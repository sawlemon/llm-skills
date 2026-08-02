// Minimal Chrome DevTools Protocol client over the loopback-only debug port
// exposed by `npm run cherry:debug`. No external dependencies: uses Node's
// built-in fetch and WebSocket.

const DEBUG_PORT = Number(process.env.CHERRY_DEBUG_PORT || 9223);
const DEBUG_HOST = "127.0.0.1";

class CdpError extends Error {}

async function listTargets() {
  const url = `http://${DEBUG_HOST}:${DEBUG_PORT}/json`;
  let res;
  try {
    res = await fetch(url, { signal: AbortSignal.timeout(3000) });
  } catch (err) {
    throw new CdpError(
      `Cannot reach Cherry Studio debug port ${DEBUG_PORT} (${err.message}). ` +
        `Cherry Studio must be running with --remote-debugging-port=${DEBUG_PORT}. ` +
        `Run: npm run cherry:debug`
    );
  }
  if (!res.ok) {
    throw new CdpError(`Debug port responded with HTTP ${res.status}`);
  }
  return res.json();
}

/** Pick the main renderer page target (not devtools, not the mini window). */
function pickMainPageTarget(targets) {
  const pages = targets.filter((t) => t.type === "page" && /index\.html(\?|$)/.test(t.url || ""));
  if (pages.length === 0) {
    throw new CdpError(
      `No Cherry Studio main-window page target found among ${targets.length} debug targets. ` +
        `Is the main window open (not just tray/mini window)?`
    );
  }
  // Prefer a target whose URL does not reference the miniWindow/selection html files.
  const best = pages.find((t) => !/mini|selection/i.test(t.url)) || pages[0];
  return best;
}

class CdpSession {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    this.ws.addEventListener("message", (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data.toString());
      } catch {
        return;
      }
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new CdpError(msg.error.message || "CDP error"));
        else resolve(msg.result);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(payload);
    });
  }

  /**
   * Evaluate an async expression in the page context and return its value by
   * value (JSON round-trip via CDP). `expression` should be a `(async () =>
   * { ... })()` IIFE string; wrapping is left to the caller so it can decide
   * indentation/comments freely.
   */
  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout: 30000,
    });
    if (result.exceptionDetails) {
      const detail = result.exceptionDetails;
      const text =
        detail.exception?.description || detail.exception?.value || detail.text || "evaluation threw";
      throw new CdpError(`Page evaluation failed: ${text}`);
    }
    return result.result?.value;
  }

  close() {
    this.ws.close();
  }
}

/** Connect to the running Cherry Studio main window over CDP. */
export async function connect() {
  const targets = await listTargets();
  const target = pickMainPageTarget(targets);
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve(), { once: true });
    ws.addEventListener("error", (e) => reject(new CdpError(`WebSocket error: ${e.message || e}`)), {
      once: true,
    });
  });
  return new CdpSession(ws);
}

export { CdpError };
