#!/usr/bin/env bash
# Offline checks for the preview deploy scripts. No cloud calls.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

bash -n scripts/preview/backend.sh
bash -n scripts/preview/frontend.sh
bash -n scripts/preview/cleanup.sh

backend_out="$(
  DRY_RUN=1 PREVIEW_TAG=pr-8 GCP_PROJECT=asktemoc \
    BACKEND_JWT_SECRET=super-secret-test-value \
    bash scripts/preview/backend.sh
)"
printf '%s\n' "$backend_out"
printf '%s\n' "$backend_out" | grep -q 'asktemoc-api-preview'
printf '%s\n' "$backend_out" | grep -q -- '--no-traffic'
printf '%s\n' "$backend_out" | grep -q 'preview-pr-8'
printf '%s\n' "$backend_out" | grep -q 'deploy/.gcloudignore'
if printf '%s\n' "$backend_out" | grep -q 'super-secret-test-value'; then
  echo "backend dry-run leaked BACKEND_JWT_SECRET" >&2
  exit 1
fi
if printf '%s\n' "$backend_out" | grep -E 'gcloud run deploy asktemoc-api( |$)'; then
  echo "backend dry-run targeted the production service" >&2
  exit 1
fi

web_out="$(
  DRY_RUN=1 PREVIEW_API_URL=https://pr-8---asktemoc-api-preview.example.run.app \
    BACKEND_JWT_SECRET=super-secret-test-value \
    AUTH_SECRET=super-secret-test-value \
    bash scripts/preview/frontend.sh
)"
printf '%s\n' "$web_out"
printf '%s\n' "$web_out" | grep -q 'vercel deploy'
printf '%s\n' "$web_out" | grep -q 'ASKTEMOC_PREVIEW_API_ORIGIN=https://pr-8---asktemoc-api-preview.example.run.app'
if printf '%s\n' "$web_out" | grep -q -- '--prod'; then
  echo "frontend dry-run requested a production deploy" >&2
  exit 1
fi
if printf '%s\n' "$web_out" | grep -q 'super-secret-test-value'; then
  echo "frontend dry-run leaked a secret" >&2
  exit 1
fi

cleanup_out="$(DRY_RUN=1 PREVIEW_TAG=pr-8 bash scripts/preview/cleanup.sh)"
printf '%s\n' "$cleanup_out"
printf '%s\n' "$cleanup_out" | grep -q 'asktemoc-api-preview'
printf '%s\n' "$cleanup_out" | grep -q -- '--remove-tags pr-8'
if printf '%s\n' "$cleanup_out" | grep -E 'update-traffic asktemoc-api( |$)'; then
  echo "cleanup dry-run targeted the production service" >&2
  exit 1
fi

if PREVIEW_SERVICE=asktemoc-api DRY_RUN=1 PREVIEW_TAG=pr-8 bash scripts/preview/backend.sh >/dev/null 2>&1; then
  echo "backend script allowed a production service name" >&2
  exit 1
fi

echo "dry-run ok"
