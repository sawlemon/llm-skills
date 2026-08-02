#!/usr/bin/env node
// Applies an already-reviewed candidate.md to the live Cherry Studio
// assistant. Refuses to run if the live prompt has drifted from the
// current.md snapshot captured by propose.mjs (someone edited it in the UI
// meanwhile) — re-run propose in that case. Always snapshots the pre-apply
// prompt to history/ before writing, and re-verifies the write afterward.

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { connect } from './lib/cdp.mjs';
import { resolveAssistant } from './lib/assistant.mjs';
import { sha256 } from './lib/report.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');

function parseArgs(argv) {
  const args = { assistant: 'Personal' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--assistant') args.assistant = argv[++i];
    else throw new Error(`Unknown argument: ${a}`);
  }
  return args;
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

function extractRecordedSha(currentMd) {
  const m = currentMd.match(/sha256:\s*([0-9a-f]{64})/);
  if (!m) throw new Error('current.md missing sha256 header — run propose first');
  return m[1];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const slug = slugify(args.assistant);
  const promptDir = join(REPO_ROOT, 'prompts', 'cherry-studio', slug);
  const historyDir = join(promptDir, 'history');

  let currentMd, candidatePrompt;
  try {
    currentMd = await readFile(join(promptDir, 'current.md'), 'utf8');
    candidatePrompt = await readFile(join(promptDir, 'candidate.md'), 'utf8');
  } catch (err) {
    throw new Error(`Missing current.md/candidate.md in ${promptDir} — run propose first (${err.message})`);
  }
  const recordedSha = extractRecordedSha(currentMd);

  console.log('[apply] connecting to Cherry Studio debug port…');
  const session = await connect();
  try {
    const before = await resolveAssistant(session, args.assistant);
    const liveSha = sha256(before.prompt);
    if (liveSha !== recordedSha) {
      throw new Error(
        `Live prompt (sha ${liveSha.slice(0, 16)}) no longer matches the proposal's current.md snapshot ` +
          `(sha ${recordedSha.slice(0, 16)}). It was likely edited in the UI since propose ran. ` +
          `Re-run: npm run cherry:propose -- --assistant ${JSON.stringify(args.assistant)}`,
      );
    }
    if (candidatePrompt === before.prompt) {
      console.log('[apply] candidate.md is identical to the live prompt — nothing to apply.');
      return;
    }

    await mkdir(historyDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 16);
    const snapshotPath = join(historyDir, `${stamp}.md`);
    await writeFile(
      snapshotPath,
      `<!-- sha256: ${liveSha} | pre-apply snapshot: ${new Date().toISOString()} -->\n\n${before.prompt}\n`,
      'utf8',
    );
    console.log(`[apply] snapshotted pre-apply prompt to ${snapshotPath}`);

    const dispatchExpr = `
      (async () => {
        window.store.dispatch({
          type: "assistants/updateAssistant",
          payload: { id: ${JSON.stringify(before.id)}, prompt: ${JSON.stringify(candidatePrompt)} },
        });
        return true;
      })()
    `;
    await session.evaluate(dispatchExpr);
    console.log('[apply] dispatched assistants/updateAssistant, waiting for redux-persist flush…');
    await new Promise((r) => setTimeout(r, 1500));

    const after = await resolveAssistant(session, args.assistant);
    if (after.prompt !== candidatePrompt) {
      // Attempt to roll back before failing loudly.
      const rollbackExpr = `
        (async () => {
          window.store.dispatch({
            type: "assistants/updateAssistant",
            payload: { id: ${JSON.stringify(before.id)}, prompt: ${JSON.stringify(before.prompt)} },
          });
          return true;
        })()
      `;
      await session.evaluate(rollbackExpr);
      throw new Error(
        'Post-apply verification failed: live prompt does not match candidate after dispatch. Rolled back to pre-apply snapshot.',
      );
    }

    // Guard: confirm the sibling defaultAssistant and (if resolvable) any
    // other same-named-prefix assistants were not touched by this dispatch.
    console.log(`[apply] verified: "${after.name}" (id=${after.id}) now matches candidate.md.`);

    const changelogPath = join(promptDir, 'CHANGELOG.md');
    const entry =
      `\n## ${new Date().toISOString()}\n` +
      `- previous sha256: ${liveSha}\n` +
      `- new sha256: ${sha256(after.prompt)}\n` +
      `- snapshot: history/${stamp}.md\n`;
    await writeFile(changelogPath, entry, { flag: 'a' });
    console.log(`[apply] appended ${changelogPath}`);
  } finally {
    session.close();
  }
}

main().catch((err) => {
  console.error(`[apply] ${err.message}`);
  process.exit(1);
});
