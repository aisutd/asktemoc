#!/usr/bin/env bash
# Build the re-scrape image, deploy it as a Cloud Run Job, and schedule it weekly with Cloud Scheduler.
# Prereqs: gcloud CLI, APIs enabled (Cloud Build, Cloud Run, Cloud Scheduler, Artifact Registry).
#
# The job needs DATABASE_URL and OPENAI_API_KEY. Put them in Secret Manager and name the secrets here:
#   export DATABASE_URL_SECRET=asktemoc-database-url
#   export OPENAI_API_KEY_SECRET=asktemoc-openai-api-key
#
# Cloud Scheduler calls the Cloud Run Admin API as a service account that has roles/run.invoker on the job:
#   export SCHEDULER_SA=asktemoc-scheduler@my-project-id.iam.gserviceaccount.com
#
# Usage (from backend/):
#   export GCP_PROJECT=my-project-id GCP_REGION=us-central1
#   bash deploy/deploy_rescrape_job.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
JOB="${RESCRAPE_JOB:-asktemoc-rescrape}"
ARTIFACT_REPO="${ARTIFACT_REPO:-asktemoc-api}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${ARTIFACT_REPO}/rescrape:latest"
SCHEDULE="${RESCRAPE_SCHEDULE:-0 2 * * 0}"          # Sundays 02:00
TIME_ZONE="${RESCRAPE_TIME_ZONE:-America/Chicago}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "Set GCP_PROJECT or: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi
: "${DATABASE_URL_SECRET:?name the Secret Manager secret that holds DATABASE_URL}"
: "${OPENAI_API_KEY_SECRET:?name the Secret Manager secret that holds OPENAI_API_KEY}"
: "${SCHEDULER_SA:?set the service account Cloud Scheduler runs as}"

gcloud config set project "${PROJECT}"

echo "Building and pushing: ${IMAGE}"
gcloud builds submit "${ROOT}" \
  --config "${ROOT}/deploy/cloudbuild-rescrape.yaml" \
  --ignore-file "${ROOT}/deploy/.gcloudignore" \
  --substitutions "_IMAGE=${IMAGE}"

# max-retries 0: exit code 2 means a guard stopped the run on purpose, so retrying would only repeat it.
gcloud run jobs deploy "${JOB}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --memory 2Gi \
  --cpu 1 \
  --task-timeout 3600s \
  --max-retries 0 \
  --set-secrets "DATABASE_URL=${DATABASE_URL_SECRET}:latest,OPENAI_API_KEY=${OPENAI_API_KEY_SECRET}:latest" \
  --set-env-vars "ENVIRONMENT=production"

URI="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run"
SCHED_ARGS=(--location "${REGION}" --schedule "${SCHEDULE}" --time-zone "${TIME_ZONE}"
  --uri "${URI}" --http-method POST --oauth-service-account-email "${SCHEDULER_SA}")
if gcloud scheduler jobs describe "${JOB}-weekly" --location "${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${JOB}-weekly" "${SCHED_ARGS[@]}"
else
  gcloud scheduler jobs create http "${JOB}-weekly" "${SCHED_ARGS[@]}"
fi

echo "Deployed job ${JOB}, scheduled '${SCHEDULE}' (${TIME_ZONE})."
echo "First run: gcloud run jobs execute ${JOB} --region ${REGION} --args=--dry-run   (writes nothing)"
