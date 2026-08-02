import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { apiBase, loadApiKey } from './config.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PERSONA_PATH = join(
  __dirname,
  '..',
  '..',
  '..',
  'skills',
  'hill-climb',
  'cherry-studio-personal-prompt-hillclimb.md',
);

class AnalysisError extends Error {}

async function loadPersona() {
  try {
    const raw = await readFile(PERSONA_PATH, 'utf8');
    // Strip YAML frontmatter (--- ... ---) so only the instructions body is
    // sent as the system prompt.
    return raw.replace(/^---\n[\s\S]*?\n---\n/, '').trim();
  } catch (err) {
    throw new AnalysisError(`Cannot read analyzer persona at ${PERSONA_PATH}: ${err.message}`);
  }
}

// Preferred model suffixes, in priority order, matched against the model
// id's suffix after the last ":" (Cherry Studio prefixes ids with the
// provider id, e.g. "d4528a5a-...:gpt-5.6-terra"). gpt-5.6-terra is
// verified (2026-08-02) to reliably follow the analyzer persona's
// JSON-only output contract; the first-listed provider default
// (claude-sonnet-5) was observed to ignore it and reply conversationally
// instead of returning JSON, so we do not simply take /v1/models[0].
const PREFERRED_MODEL_SUFFIXES = ['gpt-5.6-terra', 'gpt-5.6-sol', 'claude-opus-5'];

async function pickDefaultModel(apiKey) {
  const res = await fetch(`${apiBase()}/v1/models`, {
    headers: { Authorization: `Bearer ${apiKey}` },
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) throw new AnalysisError(`GET /v1/models failed: HTTP ${res.status}`);
  const body = await res.json();
  const available = body.data || [];
  if (available.length === 0) throw new AnalysisError('No models returned by Cherry Studio API server');
  for (const suffix of PREFERRED_MODEL_SUFFIXES) {
    const match = available.find((m) => m.id.endsWith(`:${suffix}`) || m.id === suffix);
    if (match) return match.id;
  }
  return available[0].id;
}

const RESPONSE_SHAPE_KEYS = ['learnings', 'rejected', 'prompt_edits', 'candidate_prompt'];

function validateShape(obj) {
  for (const key of RESPONSE_SHAPE_KEYS) {
    if (!(key in obj)) throw new AnalysisError(`Analyzer response missing required key "${key}"`);
  }
  if (!Array.isArray(obj.learnings) || !Array.isArray(obj.rejected) || !Array.isArray(obj.prompt_edits)) {
    throw new AnalysisError('Analyzer response learnings/rejected/prompt_edits must be arrays');
  }
  if (typeof obj.candidate_prompt !== 'string') {
    throw new AnalysisError('Analyzer response candidate_prompt must be a string');
  }
}

/**
 * Drops any "confirmed" learning whose evidence.quote is not found verbatim
 * in the supplied transcript text for the cited messageId. This is the
 * evidence-gate enforcement point — the analyzer LLM is instructed not to
 * fabricate quotes, but we do not trust it and verify programmatically.
 */
function enforceEvidenceGate(analysis, transcript) {
  const textByMessageId = new Map(transcript.map((r) => [r.messageId, r.text]));
  const kept = [];
  const droppedAsUnverified = [];
  for (const learning of analysis.learnings) {
    const quote = learning.evidence?.quote;
    const messageId = learning.evidence?.messageId;
    const sourceText = textByMessageId.get(messageId);
    const verified =
      typeof quote === 'string' && quote.length > 0 && sourceText && sourceText.includes(quote);
    if (verified) {
      kept.push(learning);
    } else {
      droppedAsUnverified.push({ ...learning, reason: 'quote not found verbatim in transcript' });
    }
  }
  const confirmedIds = new Set(
    kept
      .filter((l) => l.confidence === 'confirmed')
      .map((l) => l.evidence.messageId + '|' + l.evidence.quote),
  );
  // If nothing survives verification as confirmed, prompt_edits must be
  // discarded and candidate_prompt forced back to the original — the LLM
  // may have hallucinated edits off unverifiable evidence.
  const anyConfirmed = kept.some((l) => l.confidence === 'confirmed');
  return {
    learnings: kept,
    rejected: [
      ...analysis.rejected,
      ...droppedAsUnverified.map((d) => ({ candidate: d.claim, reason: d.reason })),
    ],
    prompt_edits: anyConfirmed ? analysis.prompt_edits : [],
    candidate_prompt: anyConfirmed ? analysis.candidate_prompt : null, // caller substitutes original
    hasConfirmedLearnings: anyConfirmed,
  };
}

/**
 * @param {{currentPrompt: string, transcript: object[], model?: string}} opts
 */
export async function analyze({ currentPrompt, transcript, model }) {
  const apiKey = await loadApiKey();
  const persona = await loadPersona();
  const chosenModel = model || (await pickDefaultModel(apiKey));

  const userPayload = {
    current_system_prompt: currentPrompt,
    transcript,
  };

  const res = await fetch(`${apiBase()}/v1/chat/completions`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: chosenModel,
      stream: false,
      messages: [
        { role: 'system', content: persona },
        { role: 'user', content: JSON.stringify(userPayload) },
      ],
    }),
    signal: AbortSignal.timeout(180000),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new AnalysisError(`POST /v1/chat/completions failed: HTTP ${res.status} ${body.slice(0, 500)}`);
  }

  const body = await res.json();
  const content = body.choices?.[0]?.message?.content;
  if (!content) throw new AnalysisError('Analyzer returned no message content');

  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch (err) {
    throw new AnalysisError(
      `Analyzer did not return valid JSON: ${err.message}\nRaw: ${content.slice(0, 500)}`,
    );
  }
  validateShape(parsed);

  const verified = enforceEvidenceGate(parsed, transcript);
  if (!verified.hasConfirmedLearnings) {
    verified.candidate_prompt = currentPrompt;
  }
  return { ...verified, model: chosenModel };
}

export { AnalysisError };
