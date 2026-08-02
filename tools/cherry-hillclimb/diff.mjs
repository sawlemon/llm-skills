#!/usr/bin/env node
// Prints the diff between the last-proposed current.md and candidate.md
// without touching the live app.

import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { simpleDiff } from "./lib/report.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");

function parseArgs(argv) {
  const args = { assistant: "Personal" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--assistant") args.assistant = argv[++i];
    else throw new Error(`Unknown argument: ${a}`);
  }
  return args;
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const slug = slugify(args.assistant);
  const promptDir = join(REPO_ROOT, "prompts", "cherry-studio", slug);
  const currentMd = (await readFile(join(promptDir, "current.md"), "utf8")).replace(/^<!--[\s\S]*?-->\n\n/, "");
  const candidateMd = await readFile(join(promptDir, "candidate.md"), "utf8");
  console.log(simpleDiff(currentMd, candidateMd));
}

main().catch((err) => {
  console.error(`[diff] ${err.message}`);
  process.exit(1);
});
