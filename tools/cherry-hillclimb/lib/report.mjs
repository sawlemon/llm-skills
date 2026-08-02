import { createHash } from "node:crypto";

export function sha256(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

/** Very small unified-diff-style line renderer (not a real LCS diff — good
 * enough for human review of a system prompt, not meant to be `patch`-able). */
export function simpleDiff(before, after) {
  if (before === after) return "(no changes)";
  const a = before.split("\n");
  const b = after.split("\n");
  const max = Math.max(a.length, b.length);
  const lines = [];
  for (let i = 0; i < max; i++) {
    const la = a[i];
    const lb = b[i];
    if (la === lb) {
      if (la !== undefined) lines.push(`  ${la}`);
      continue;
    }
    if (la !== undefined) lines.push(`- ${la}`);
    if (lb !== undefined) lines.push(`+ ${lb}`);
  }
  return lines.join("\n");
}

export function renderReport({ date, assistantName, hours, topicsScanned, transcriptCount, analysis, diff }) {
  const lines = [];
  lines.push(`# Cherry Hillclimb report — ${date}`);
  lines.push("");
  lines.push(`- Assistant: ${assistantName}`);
  lines.push(`- Window: last ${hours}h`);
  lines.push(`- Topics scanned: ${topicsScanned}`);
  lines.push(`- Messages with text extracted: ${transcriptCount}`);
  lines.push(`- Analyzer model: ${analysis.model}`);
  lines.push("");
  lines.push(`## Learnings (${analysis.learnings.length})`);
  if (analysis.learnings.length === 0) {
    lines.push("_None._");
  } else {
    for (const l of analysis.learnings) {
      lines.push(
        `- [${l.confidence}] (${l.category}) ${l.claim}\n  evidence: topic \`${l.evidence.topicId}\` message \`${l.evidence.messageId}\`: "${l.evidence.quote}"`
      );
    }
  }
  lines.push("");
  lines.push(`## Rejected (${analysis.rejected.length})`);
  if (analysis.rejected.length === 0) {
    lines.push("_None._");
  } else {
    for (const r of analysis.rejected) {
      lines.push(`- ${r.candidate} — ${r.reason}`);
    }
  }
  lines.push("");
  lines.push(`## Prompt edits (${analysis.prompt_edits.length})`);
  if (analysis.prompt_edits.length === 0) {
    lines.push("_None — candidate_prompt is unchanged from current.md._");
  } else {
    for (const e of analysis.prompt_edits) {
      lines.push(`- **${e.op}** ${e.section}: ${e.because}`);
    }
    lines.push("");
    lines.push("### Diff (current.md → candidate.md)");
    lines.push("```diff");
    lines.push(diff);
    lines.push("```");
  }
  lines.push("");
  return lines.join("\n");
}
