#!/usr/bin/env bash
# Build the FastAPI image and deploy it to the preview Cloud Run service.
# The production service is only read, so its traffic and env stay put.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
DRY_RUN="${DRY_RUN:-0}"
PROJECT="${GCP_PROJECT:-asktemoc}"
REGION="${GCP_REGION:-us-central1}"
SOURCE_SERVICE="${CLOUD_RUN_SERVICE:-asktemoc-api}"
SERVICE="${PREVIEW_SERVICE:-asktemoc-api-preview}"
ARTIFACT_REPO="${ARTIFACT_REPO:-asktemoc-api}"
SKIP_BUILD="${SKIP_BUILD:-0}"

if [[ -z "${PREVIEW_TAG:-}" ]]; then
  if [[ -n "${PR_NUMBER:-}" ]]; then
    PREVIEW_TAG="pr-${PR_NUMBER}"
  else
    sha="${GITHUB_SHA:-$(git -C "$ROOT" rev-parse --short=7 HEAD)}"
    PREVIEW_TAG="sha-${sha:0:7}"
  fi
fi
TAG="$(printf '%s' "$PREVIEW_TAG" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"
TAG="${TAG#-}"
TAG="${TAG%-}"
if [[ ! "$TAG" =~ ^[a-z][a-z0-9-]{0,45}$ ]]; then
  echo "PREVIEW_TAG must be a lowercase DNS label (for example pr-8)" >&2
  exit 1
fi
if [[ "$SERVICE" == "$SOURCE_SERVICE" ]]; then
  echo "Refusing to deploy preview onto the production service ${SOURCE_SERVICE}" >&2
  exit 1
fi

if [[ "${PREVIEW_LOAD_LOCAL_ENV:-0}" == "1" && -z "${BACKEND_JWT_SECRET:-}" && -f "$BACKEND/.env" ]]; then
  BACKEND_JWT_SECRET="$(
    ENV_FILE="$BACKEND/.env" python3 - <<'PY'
import os
for raw in open(os.environ["ENV_FILE"]):
    line = raw.strip()
    if line.startswith("BACKEND_JWT_SECRET="):
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        print(value, end="")
        break
PY
  )"
  export BACKEND_JWT_SECRET
fi

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${ARTIFACT_REPO}/backend:preview-${TAG}"
RESULT_DIR="${RUNNER_TEMP:-/tmp}"
RESULT_FILE="$RESULT_DIR/asktemoc-preview-api-url"

log() { printf '%s\n' "$*" >&2; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf 'DRY_RUN'
    local arg
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    printf '\n'
    return 0
  fi
  "$@"
}

traffic_json() {
  local service="$1"
  gcloud run services describe "$service" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format='json(status.traffic)'
}

write_env_file() {
  local dest="$1"
  local prod_json="$2"
  python3 - "$dest" "$prod_json" <<'PY'
import json, os, sys
dest, prod_path = sys.argv[1], sys.argv[2]
data = json.load(open(prod_path))
env = (((data.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers", [{}])[0].get("env") or []
values = {}
for item in env:
    name = item.get("name")
    if not name:
        continue
    if "valueFrom" in item:
        sys.exit(f"production env {name} is a secret reference; preview copy supports plain values only")
    values[name] = item.get("value", "")
values["ENVIRONMENT"] = "preview"
values["LLM_PROVIDER"] = values.get("LLM_PROVIDER") or "openai"
origins = ["http://localhost:3000"]
web = os.environ.get("PREVIEW_WEB_ORIGIN", "").strip().rstrip("/")
if web:
    origins.append(web)
values["CORS_ORIGINS"] = ",".join(origins)
secret = os.environ.get("BACKEND_JWT_SECRET", "")
if secret:
    values["BACKEND_JWT_SECRET"] = secret

def quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'

with open(dest, "w") as fh:
    for key in sorted(values):
        fh.write(f"{key}: {quote(values[key])}\n")
os.chmod(dest, 0o600)
PY
}

preview_url() {
  local service_url="$1"
  local host="${service_url#https://}"
  host="${host#http://}"
  printf 'https://%s---%s\n' "$TAG" "$host"
}

if [[ "$DRY_RUN" == "1" ]]; then
  log "preview service=${SERVICE} tag=${TAG} image=${IMAGE}"
  if [[ "$SKIP_BUILD" != "1" ]]; then
    run gcloud builds submit "$BACKEND" \
      --project "$PROJECT" \
      --config "$BACKEND/deploy/cloudbuild.yaml" \
      --ignore-file "$BACKEND/deploy/.gcloudignore" \
      --substitutions "_IMAGE=${IMAGE}"
  fi
  run gcloud run deploy "$SERVICE" \
    --project "$PROJECT" \
    --image "$IMAGE" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --no-traffic \
    --tag "$TAG" \
    --env-vars-file "redacted" \
    --quiet
  printf 'PREVIEW_API_URL=%s\n' "https://${TAG}---${SERVICE}-example.a.run.app"
  exit 0
fi

prod_before="$(mktemp)"
traffic_json "$SOURCE_SERVICE" > "$prod_before"
env_json="$(mktemp)"
env_file="$(mktemp)"
trap 'rm -f "$prod_before" "$env_json" "$env_file"' EXIT
gcloud run services describe "$SOURCE_SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --format='json(spec.template.spec.containers[0].env)' > "$env_json"
write_env_file "$env_file" "$env_json"

if [[ "$SKIP_BUILD" != "1" ]]; then
  log "Building ${IMAGE}"
  gcloud builds submit "$BACKEND" \
    --project "$PROJECT" \
    --config "$BACKEND/deploy/cloudbuild.yaml" \
    --ignore-file "$BACKEND/deploy/.gcloudignore" \
    --substitutions "_IMAGE=${IMAGE}" \
    --quiet
fi

exists=0
if gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(metadata.name)' >/dev/null 2>&1; then
  exists=1
fi

log "Deploying ${SERVICE} tag=${TAG} (production ${SOURCE_SERVICE} is not updated)"
deploy_args=(
  gcloud run deploy "$SERVICE"
  --project "$PROJECT"
  --image "$IMAGE"
  --region "$REGION"
  --platform managed
  --allow-unauthenticated
  --port 8080
  --memory 1Gi
  --cpu 1
  --min-instances 0
  --max-instances 3
  --tag "$TAG"
  --env-vars-file "$env_file"
  --quiet
)
if [[ "$exists" == "1" ]]; then
  deploy_args+=(--no-traffic)
fi
"${deploy_args[@]}"

service_url="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
url="$(preview_url "$service_url")"
printf '%s\n' "$url" > "$RESULT_FILE"
printf 'PREVIEW_API_URL=%s\n' "$url"

prod_after="$(mktemp)"
traffic_json "$SOURCE_SERVICE" > "$prod_after"
if ! cmp -s "$prod_before" "$prod_after"; then
  echo "Production traffic changed during preview deploy" >&2
  exit 1
fi
rm -f "$prod_after"

log "Checking ${url}/api/health/"
ok=0
for _ in 1 2 3 4 5 6 7 8; do
  if curl -fsS --max-time 20 "${url}/api/health/" >/dev/null; then
    ok=1
    break
  fi
  sleep 8
done
if [[ "$ok" != "1" ]]; then
  echo "Preview API did not become healthy: ${url}/api/health/" >&2
  exit 1
fi
log "Preview API healthy"
