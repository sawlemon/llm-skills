import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

const API_BASE = process.env.CHERRY_API_BASE || "http://127.0.0.1:23333";
const ENV_FILE = join(homedir(), ".cherry-hillclimb.env");

/** Loads CHERRY_API_KEY from process.env, falling back to a git-ignored
 * dotenv-style file at ~/.cherry-hillclimb.env (KEY=value per line). Never
 * echoes the key value in logs. */
export async function loadApiKey() {
  if (process.env.CHERRY_API_KEY) return process.env.CHERRY_API_KEY;
  try {
    const raw = await readFile(ENV_FILE, "utf8");
    for (const line of raw.split("\n")) {
      const m = line.match(/^\s*CHERRY_API_KEY\s*=\s*(.+?)\s*$/);
      if (m) return m[1].replace(/^["']|["']$/g, "");
    }
  } catch {
    // file absent is fine, fall through to the error below
  }
  throw new Error(
    `CHERRY_API_KEY not set. Export it or write it to ${ENV_FILE} as CHERRY_API_KEY=cs-sk-...\n` +
      `Find the current key in Cherry Studio: Settings > API Server.`
  );
}

export function apiBase() {
  return API_BASE;
}
