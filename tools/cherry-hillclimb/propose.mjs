#!/usr/bin/env node
// Daily hillclimb proposal: reads the last N hours of the target assistant's
// Cherry Studio conversations, runs them through the analyzer persona, and
// writes review artifacts under prompts/cherry-studio/<slug>/ and
// reports/cherry-hillclimb/. Never applies anything to the live app — see
// apply.mjs for that step.

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { connect } from './lib/cdp.mjs';
import { resolveAssistant } from './lib/assistant.mjs';
import { extractTranscript } from './lib/extract.mjs';
import { analyze } from './lib/analyze.mjs';
import { sha256, simpleDiff, renderReport } from './lib/report.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');

function parseArgs(argv) {
  const args = { hours: 24, assistant: 'Personal', model: undefined, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--hours') args.hours = Number(argv[++i]);
    else if (a === '--assistant') args.assistant = argv[++i];
    else if (a === '--model') args.model = argv[++i];
    else if (a === '--dry-run') args.dryRun = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  if (!Number.isFinite(args.hours) || args.hours < 0) {
    throw new Error('--hours must be a non-negative number');
  }
  return args;
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const slug = slugify(args.assistant);
  const promptDir = join(REPO_ROOT, 'prompts', 'cherry-studio', slug);
  const historyDir = join(promptDir, 'history');
  const reportDir = join(REPO_ROOT, 'reports', 'cherry-hillclimb');
  await mkdir(historyDir, { recursive: true });
  await mkdir(reportDir, { recursive: true });

  console.log(`[propose] connecting to Cherry Studio debug port…`);
  const session = await connect();
  let assistant;
  try {
    assistant = await resolveAssistant(session, args.assistant);
    console.log(
      `[propose] resolved "${assistant.name}" (id=${assistant.id}, promptSha=${sha256(assistant.prompt).slice(
        0,
        16,
      )}, topics=${assistant.topics.length})`,
    );

    console.log(`[propose] extracting last ${args.hours}h of transcript…`);
    const transcript = await extractTranscript(session, assistant, args.hours);
    console.log(`[propose] extracted ${transcript.length} message(s) with text`);

    const currentPath = join(promptDir, 'current.md');
    const currentMd = `<!-- sha256: ${sha256(assistant.prompt)} | captured: ${new Date().toISOString()} -->\n\n${
      assistant.prompt
    }\n`;
    await writeFile(currentPath, currentMd, 'utf8');

    if (args.dryRun) {
      console.log('[propose] --dry-run: skipping analyzer call. Extraction verified above.');
      return;
    }

    if (transcript.length === 0) {
      console.log('[propose] no in-scope messages in window — writing empty report, no candidate.');
      const date = new Date().toISOString().slice(0, 10);
      const report = renderReport({
        date,
        assistantName: assistant.name,
        hours: args.hours,
        topicsScanned: 0,
        transcriptCount: 0,
        analysis: { model: '(skipped — empty transcript)', learnings: [], rejected: [], prompt_edits: [] },
        diff: '(no changes)',
      });
      await writeFile(join(reportDir, `${date}-${slug}.md`), report, 'utf8');
      return;
    }

    console.log(`[propose] sending to analyzer (model=${args.model || '(default)'})…`);
    const analysis = await analyze({ currentPrompt: assistant.prompt, transcript, model: args.model });

    const candidatePath = join(promptDir, 'candidate.md');
    await writeFile(candidatePath, analysis.candidate_prompt, 'utf8');

    const diff = simpleDiff(assistant.prompt, analysis.candidate_prompt);
    const date = new Date().toISOString().slice(0, 10);
    const scannedTopicIds = new Set(transcript.map((r) => r.topicId));
    const report = renderReport({
      date,
      assistantName: assistant.name,
      hours: args.hours,
      topicsScanned: scannedTopicIds.size,
      transcriptCount: transcript.length,
      analysis,
      diff,
    });
    await writeFile(join(reportDir, `${date}-${slug}.md`), report, 'utf8');

    console.log(`[propose] wrote ${currentPath}`);
    console.log(`[propose] wrote ${candidatePath} (${analysis.prompt_edits.length} edit(s))`);
    console.log(`[propose] wrote ${join(reportDir, `${date}-${slug}.md`)}`);
    if (analysis.prompt_edits.length > 0) {
      console.log(
        `[propose] review the diff, then run: npm run cherry:apply -- --assistant ${JSON.stringify(args.assistant)}`,
      );
    } else {
      console.log('[propose] no confirmed learnings justified a prompt change.');
    }
  } finally {
    session.close();
  }
}

main().catch((err) => {
  console.error(`[propose] ${err.message}`);
  process.exit(1);
});
