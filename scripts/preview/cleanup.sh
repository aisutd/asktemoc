#!/usr/bin/env bash
# Remove one preview tag from the preview Cloud Run service. Production is not modified.
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
PROJECT="${GCP_PROJECT:-asktemoc}"
REGION="${GCP_REGION:-us-central1}"
SOURCE_SERVICE="${CLOUD_RUN_SERVICE:-asktemoc-api}"
SERVICE="${PREVIEW_SERVICE:-asktemoc-api-preview}"
TAG="$(printf '%s' "${PREVIEW_TAG:-}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-')"

if [[ -z "$TAG" ]]; then
  echo "PREVIEW_TAG is required" >&2
  exit 1
fi
if [[ "$SERVICE" == "$SOURCE_SERVICE" ]]; then
  echo "Refusing to update traffic on the production service" >&2
  exit 1
fi

if [[ "$DRY_RUN" == "1" ]]; then
  printf 'DRY_RUN gcloud run services update-traffic %q --project %q --region %q --remove-tags %q --quiet\n' \
    "$SERVICE" "$PROJECT" "$REGION" "$TAG"
  exit 0
fi

gcloud run services update-traffic "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --remove-tags "$TAG" \
  --quiet
