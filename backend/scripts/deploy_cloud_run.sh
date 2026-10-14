#!/usr/bin/env bash
# Build with Cloud Build and deploy to Cloud Run.
# Prereqs: gcloud CLI, APIs enabled (Cloud Build, Cloud Run, Artifact Registry or Container Registry),
#          billing on the project.
#
# Before first deploy, set env/secrets in Cloud Run for at least:
#   DATABASE_URL (Neon Postgres), OPENAI_API_KEY, CORS_ORIGINS (your front-end origin(s))
#
# Usage:
#   export GCP_PROJECT=my-project-id
#   export GCP_REGION=us-central1
#   bash scripts/deploy_cloud_run.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE="${CLOUD_RUN_SERVICE:-asktemoc-api}"
ARTIFACT_REPO="${ARTIFACT_REPO:-asktemoc-api}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${ARTIFACT_REPO}/backend:latest"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "Set GCP_PROJECT or: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

gcloud config set project "${PROJECT}"
echo "Building and pushing: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" "${ROOT}"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars "LLM_PROVIDER=openai"

echo "Deployed. Set secrets/env in console: ${SERVICE} → Edit & deploy → Variables & secrets"
echo "Required: DATABASE_URL, OPENAI_API_KEY. Recommended: CORS_ORIGINS=https://your-frontend"
