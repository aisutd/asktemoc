#!/usr/bin/env bash
# Dev tasks for macOS / Linux / Git Bash. Windows PowerShell: scripts/dev.ps1.
#
#   scripts/dev.sh setup   create backend/.venv, install deps, copy .env examples
#   scripts/dev.sh seed    load data/catalog into the vector store
#   scripts/dev.sh api     run the FastAPI app on :8000 (auto-reload)
#   scripts/dev.sh web     run the Next.js app on :3000
#   scripts/dev.sh test    backend pytest + frontend lint and build
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

venv_python() {
  if [ -x "$BACKEND/.venv/bin/python" ]; then echo "$BACKEND/.venv/bin/python"
  elif [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then echo "$BACKEND/.venv/Scripts/python.exe"
  else echo "backend/.venv not found; run: scripts/dev.sh setup" >&2; exit 1
  fi
}

find_python311() {
  for cmd in python3.11 "py -3.11" python3 python; do
    if $cmd -c 'import sys; sys.exit(sys.version_info[:2] != (3, 11))' 2>/dev/null; then
      echo "$cmd"; return
    fi
  done
  echo "Python 3.11 not found" >&2; exit 1
}

copy_if_missing() {
  if [ ! -f "$2" ]; then cp "$1" "$2"; echo "created ${2#"$ROOT"/} (fill it in)"; fi
}

case "${1:-}" in
  setup)
    py="$(find_python311)"
    [ -d "$BACKEND/.venv" ] || $py -m venv "$BACKEND/.venv"
    "$(venv_python)" -m pip install --upgrade pip
    "$(venv_python)" -m pip install -r "$BACKEND/requirements-dev.txt"
    (cd "$FRONTEND" && npm ci)
    copy_if_missing "$BACKEND/.env.example" "$BACKEND/.env"
    copy_if_missing "$FRONTEND/.env.example" "$FRONTEND/.env.local"
    ;;
  seed)
    (cd "$BACKEND" && "$(venv_python)" scripts/seed_catalog.py "${@:2}")
    ;;
  api)
    (cd "$BACKEND" && "$(venv_python)" -m uvicorn app.main:app --reload --port 8000)
    ;;
  web)
    (cd "$FRONTEND" && npm run dev)
    ;;
  test)
    (cd "$BACKEND" && "$(venv_python)" -m pytest)
    (cd "$FRONTEND" && npm run lint && npm run build)
    ;;
  *)
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
