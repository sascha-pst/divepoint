#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [[ ! -x backend/.venv/bin/uvicorn || ! -f game/node_modules/vite/bin/vite.js ]]; then
  echo 'Install dependencies first: uv sync --project backend && npm install --prefix game'
  exit 1
fi
api_pid=''
game_pid=''
cleanup() {
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$game_pid" ]] || kill "$game_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
api_pid=$!
(cd game && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --strictPort) &
game_pid=$!
echo 'Divepoint: http://127.0.0.1:5173 — press Ctrl+C to stop both servers.'
# Poll both children so an API bind failure cannot leave an apparently working client.
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$game_pid" 2>/dev/null; do
  sleep 1
done
exit 1
