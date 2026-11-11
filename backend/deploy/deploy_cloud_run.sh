#!/usr/bin/env bash
# Build with Cloud Build and deploy to the production Cloud Run service.
# CI runs this on every push to main (.github/workflows/deploy-backend.yml);
# it also works by hand.
#
# Prereqs: gcloud CLI, APIs enabled (Cloud Build, Cloud Run, Artifact Registry),
#          billing on the project.
#
# Env/secrets live on the Cloud Run service (DATABASE_URL, OPENAI_API_KEY,
# BACKEND_JWT_SECRET, CORS_ORIGINS, ...). This script never replaces them: it
# only merges LLM_PROVIDER in with --update-env-vars, so existing values carry
# over from the previous revision.
#
# Images are tagged with the commit SHA, so every revision maps to a commit.
# Roll back by redeploying an earlier tag:
#   IMAGE_TAG=<old-sha> SKIP_BUILD=1 bash deploy/deploy_cloud_run.sh
#
# Usage (from backend/):
#   export GCP_PROJECT=my-project-id
#   export GCP_REGION=us-central1
#   bash deploy/deploy_cloud_run.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-asktemoc-api}"
ARTIFACT_REPO="${ARTIFACT_REPO:-asktemoc-api}"
SKIP_BUILD="${SKIP_BUILD:-0}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "Set GCP_PROJECT or: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

if [[ -z "${IMAGE_TAG:-}" ]]; then
  sha="${GITHUB_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"
  IMAGE_TAG="${sha:0:12}"
  # A local build from a dirty tree is not that commit; never overwrite its tag.
  if [[ -z "${GITHUB_SHA:-}" && -n "$(git -C "$ROOT" status --porcelain -- .)" ]]; then
    IMAGE_TAG="${IMAGE_TAG}-dirty-$(date +%Y%m%d%H%M%S)"
  fi
fi
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${ARTIFACT_REPO}/backend:${IMAGE_TAG}"

if [[ "$SKIP_BUILD" != "1" ]]; then
  echo "Building and pushing: ${IMAGE}"
  gcloud builds submit "${ROOT}" \
    --project "${PROJECT}" \
    --config "${ROOT}/deploy/cloudbuild.yaml" \
    --ignore-file "${ROOT}/deploy/.gcloudignore" \
    --substitutions "_IMAGE=${IMAGE}" \
    --quiet
fi

# Stage the revision with no traffic under the "candidate" tag, check its
# health there, and only then move production traffic to it. A revision that
# fails the check never serves users.
echo "Staging ${IMAGE} on ${SERVICE} (no traffic yet)"
gcloud run deploy "${SERVICE}" \
  --no-traffic \
  --tag candidate \
  --project "${PROJECT}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --update-env-vars "LLM_PROVIDER=openai" \
  --update-labels "commit=${IMAGE_TAG:0:63}" \
  --quiet

url="$(gcloud run services describe "${SERVICE}" --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
host="${url#https://}"
candidate="https://candidate---${host}"

echo "Checking ${candidate}/api/health/"
ok=0
for _ in 1 2 3 4 5 6 7 8; do
  if curl -fsS --max-time 20 "${candidate}/api/health/" >/dev/null; then
    ok=1
    break
  fi
  sleep 8
done
if [[ "$ok" != "1" ]]; then
  echo "Candidate did not become healthy; production traffic left unchanged: ${candidate}/api/health/" >&2
  exit 1
fi

gcloud run services update-traffic "${SERVICE}" \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --to-latest \
  --quiet

printf '%s\n' "$url" > "${RUNNER_TEMP:-/tmp}/asktemoc-api-url"
echo "Deployed ${IMAGE_TAG} to ${url}"
