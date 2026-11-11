#!/usr/bin/env bash
# Deploy frontend/ to a Vercel preview. Does not promote production.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"
API_ORIGIN="${PREVIEW_API_URL:-}"
SCOPE="${VERCEL_SCOPE:-davis118s-projects}"
PROJECT_NAME="${VERCEL_PROJECT_NAME:-asktemoc}"
RESULT_DIR="${RUNNER_TEMP:-/tmp}"
RESULT_FILE="$RESULT_DIR/asktemoc-preview-web-url"

if [[ -z "$API_ORIGIN" && -f "$RESULT_DIR/asktemoc-preview-api-url" ]]; then
  API_ORIGIN="$(cat "$RESULT_DIR/asktemoc-preview-api-url")"
fi
if [[ -z "$API_ORIGIN" ]]; then
  echo "PREVIEW_API_URL is required" >&2
  exit 1
fi
API_ORIGIN="${API_ORIGIN%/}"

if [[ "${PREVIEW_LOAD_LOCAL_ENV:-0}" == "1" ]]; then
  set -a
  eval "$(python3 - "$ROOT/backend/.env" "$ROOT/frontend/.env.local" <<'PY'
import os, sys
keys = {
    "BACKEND_JWT_SECRET",
    "AUTH_SECRET",
    "AUTH_GOOGLE_ID",
    "AUTH_GOOGLE_SECRET",
    "AUTH_MICROSOFT_ENTRA_ID_ID",
    "AUTH_MICROSOFT_ENTRA_ID_SECRET",
    "AUTH_MICROSOFT_ENTRA_ID_ISSUER",
    "ALLOWED_EMAIL_DOMAIN",
}
def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
for path in sys.argv[1:]:
    if not os.path.exists(path):
        continue
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in keys or os.environ.get(key):
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            print(f"export {key}={sh_quote(value)}")
PY
)"
  set +a
fi

vercel_args=(--scope "$SCOPE")
if [[ -n "${VERCEL_TOKEN:-}" ]]; then
  vercel_args+=(--token "$VERCEL_TOKEN")
fi

env_args=()
add_env() {
  local key="$1"
  local value="${2:-}"
  if [[ -n "$value" ]]; then
    env_args+=(-b "${key}=${value}" -e "${key}=${value}")
  fi
}
add_env ASKTEMOC_PREVIEW_API_ORIGIN "$API_ORIGIN"
add_env BACKEND_JWT_SECRET "${BACKEND_JWT_SECRET:-}"
add_env AUTH_SECRET "${AUTH_SECRET:-}"
add_env AUTH_GOOGLE_ID "${AUTH_GOOGLE_ID:-}"
add_env AUTH_GOOGLE_SECRET "${AUTH_GOOGLE_SECRET:-}"
add_env AUTH_MICROSOFT_ENTRA_ID_ID "${AUTH_MICROSOFT_ENTRA_ID_ID:-}"
add_env AUTH_MICROSOFT_ENTRA_ID_SECRET "${AUTH_MICROSOFT_ENTRA_ID_SECRET:-}"
add_env AUTH_MICROSOFT_ENTRA_ID_ISSUER "${AUTH_MICROSOFT_ENTRA_ID_ISSUER:-}"
add_env ALLOWED_EMAIL_DOMAIN "${ALLOWED_EMAIL_DOMAIN:-}"

if [[ "$DRY_RUN" == "1" ]]; then
  printf 'DRY_RUN vercel deploy --yes --cwd %q' "$ROOT"
  printf ' %q' "${vercel_args[@]}"
  local_arg=""
  for local_arg in "${env_args[@]}"; do
    case "$local_arg" in
      ASKTEMOC_PREVIEW_API_ORIGIN=*|*=http*|*=https*) printf ' %q' "$local_arg" ;;
      -b|-e) printf ' %q' "$local_arg" ;;
      *) printf ' %q' "${local_arg%%=*}=***" ;;
    esac
  done
  printf '\n'
  printf 'PREVIEW_WEB_URL=%s\n' "https://${PROJECT_NAME}-preview.vercel.app"
  exit 0
fi

cd "$ROOT"
if [[ ! -f .vercel/project.json ]]; then
  link_args=(vercel link --yes --project "$PROJECT_NAME" "${vercel_args[@]}")
  if [[ -n "${VERCEL_ORG_ID:-}" && -n "${VERCEL_PROJECT_ID:-}" ]]; then
    mkdir -p .vercel
    python3 - <<PY
import json, os
json.dump({"orgId": os.environ["VERCEL_ORG_ID"], "projectId": os.environ["VERCEL_PROJECT_ID"]}, open(".vercel/project.json", "w"))
PY
  else
    "${link_args[@]}"
  fi
fi

log="$(mktemp)"
set +e
vercel deploy --yes --cwd "$ROOT" "${vercel_args[@]}" "${env_args[@]}" >"$log" 2>&1
status=$?
set -e
python3 - "$log" <<'PY'
import os, sys
text = open(sys.argv[1]).read()
for key in (
    "BACKEND_JWT_SECRET",
    "AUTH_SECRET",
    "AUTH_GOOGLE_SECRET",
    "AUTH_MICROSOFT_ENTRA_ID_SECRET",
):
    value = os.environ.get(key, "")
    if value:
        text = text.replace(value, "***")
sys.stderr.write(text)
if not text.endswith("\n"):
    sys.stderr.write("\n")
PY
if [[ "$status" != "0" ]]; then
  exit "$status"
fi
url="$(grep -Eo 'https://[^[:space:]]+\.vercel\.app' "$log" | tail -1 || true)"
rm -f "$log"
if [[ -z "$url" ]]; then
  echo "Vercel deploy finished without a preview URL" >&2
  exit 1
fi
printf '%s\n' "$url" > "$RESULT_FILE"
printf 'PREVIEW_WEB_URL=%s\n' "$url"
