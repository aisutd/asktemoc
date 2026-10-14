#!/usr/bin/env bash
# Run uvicorn with unbuffered Python stdout/stderr so logs/uvicorn.log fills line-by-line
# (stdout piped/redirected to files is fully buffered by default, so the log can look empty).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
mkdir -p logs
LOG="${UVICORN_LOG:-$ROOT/logs/uvicorn.log}"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PY="${PYTHON:-python3}"
exec >>"$LOG" 2>&1
exec "$PY" -u -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level info
