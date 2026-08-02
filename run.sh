#!/usr/bin/env bash
# Start the FastAPI backend. Kills anything already on :8000 first so a stale
# server can never cause "Address already in use".
set -euo pipefail
cd "$(dirname "$0")"

# Free the port if something is holding it.
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
  lsof -ti tcp:8000 | xargs -r kill >/dev/null 2>&1 || true
fi
sleep 0.5

exec uvicorn app.main:app --reload
