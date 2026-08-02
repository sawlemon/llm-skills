#!/usr/bin/env bash
# Quits Cherry Studio (if running) and relaunches it with a loopback-only
# remote debugging port so the cherry-hillclimb harness can drive it over
# CDP. Safe to run whether or not the app is already open; a normal launch
# (no flag) still works fine for everyday use, it just won't have the debug
# port cherry:propose/cherry:apply need.
set -euo pipefail

PORT="${CHERRY_DEBUG_PORT:-9223}"
APP_BIN="/Applications/Cherry Studio.app/Contents/MacOS/Cherry Studio"

if [ ! -x "$APP_BIN" ]; then
  echo "error: Cherry Studio not found at $APP_BIN" >&2
  exit 1
fi

if pgrep -f "Cherry Studio.app/Contents/MacOS/Cherry Studio" >/dev/null 2>&1; then
  echo "[restart-debug] quitting running Cherry Studio..."
  osascript -e 'quit app "Cherry Studio"' >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    pgrep -f "Cherry Studio.app/Contents/MacOS/Cherry Studio" >/dev/null 2>&1 || break
    sleep 0.5
  done
fi

echo "[restart-debug] launching with --remote-debugging-port=${PORT}..."
# Launched via `open -a`, not a direct child process: this detaches Cherry
# Studio from the invoking shell/session via launchservices, so the app
# keeps running after this script's process (and its controlling terminal
# or agent session) exits. A plain `nohup ... &` here is NOT sufficient in
# some sandboxed/PTY environments, where the whole process group can be
# reaped once the invoking session ends even with nohup+disown.
open -a "/Applications/Cherry Studio.app" --args "--remote-debugging-port=$PORT"

for _ in $(seq 1 40); do
  if curl -s -m 1 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "[restart-debug] debug port $PORT is up."
    exit 0
  fi
  sleep 0.5
done

echo "error: debug port $PORT did not come up within 20s; check /tmp/cherry-studio-debug.log" >&2
exit 1
