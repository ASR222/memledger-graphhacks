#!/usr/bin/env bash
# Deploy MemLedger to Cloud Run from source (Cloud Build uses the Dockerfile).
#
#   PROJECT=my-project GEMINI_API_KEY=... MODE=embedded scripts/deploy.sh
#   PROJECT=my-project GEMINI_API_KEY=... MODE=cloud \
#     FALKORDB_HOST=... FALKORDB_PORT=... FALKORDB_PASSWORD=... scripts/deploy.sh
#
# MODE=embedded : FalkorDB runs inside the container (data lost on restart; never expires)
# MODE=cloud    : FalkorDB Cloud (free tier: stops after 1 idle day, deleted after 7)
# Optional: REGION (asia-south1), SERVICE (memledger), EXTRACT (cache), AGENTS (live),
#           FALKORDB_USERNAME (falkordb), ALLOW_RESET (1)
set -euo pipefail

: "${PROJECT:?set PROJECT to your GCP project id}"
: "${GEMINI_API_KEY:?set GEMINI_API_KEY}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-memledger}"
MODE="${MODE:-embedded}"
EXTRACT="${EXTRACT:-cache}"
AGENTS="${AGENTS:-live}"
ALLOW_RESET="${ALLOW_RESET:-1}"

case "$MODE" in embedded|cloud) ;; *) echo "MODE must be embedded or cloud" >&2; exit 2 ;; esac
if [[ "$EXTRACT" == "cache" && ! -f data/.extract_cache.json ]]; then
  echo "EXTRACT=cache but data/.extract_cache.json is missing: do one live run first (SCN.md §6)," >&2
  echo "or deploy with EXTRACT=live." >&2
  exit 2
fi

gcloud config set project "$PROJECT" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

NUM="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${NUM}-compute@developer.gserviceaccount.com"

# Source deploys build with the Compute Engine default service account.
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role=roles/run.builder --condition=None >/dev/null

secret() {   # secret NAME VALUE: create or add a version, and let the service read it
  if gcloud secrets describe "$1" >/dev/null 2>&1; then
    printf '%s' "$2" | gcloud secrets versions add "$1" --data-file=- >/dev/null
  else
    printf '%s' "$2" | gcloud secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$1" --member="serviceAccount:${SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
}

secret memledger-gemini-key "$GEMINI_API_KEY"
ENV_VARS="MEMLEDGER_EXTRACT=${EXTRACT},MEMLEDGER_AGENTS=${AGENTS},MEMLEDGER_ALLOW_RESET=${ALLOW_RESET}"
SECRETS="GEMINI_API_KEY=memledger-gemini-key:latest"

if [[ "$MODE" == "embedded" ]]; then
  ENV_VARS="${ENV_VARS},MEMLEDGER_EMBEDDED_DB=1"
else
  : "${FALKORDB_HOST:?set FALKORDB_HOST}" "${FALKORDB_PORT:?set FALKORDB_PORT}" "${FALKORDB_PASSWORD:?set FALKORDB_PASSWORD}"
  secret memledger-falkordb-password "$FALKORDB_PASSWORD"
  ENV_VARS="${ENV_VARS},FALKORDB_HOST=${FALKORDB_HOST},FALKORDB_PORT=${FALKORDB_PORT},FALKORDB_USERNAME=${FALKORDB_USERNAME:-falkordb}"
  SECRETS="${SECRETS},FALKORDB_PASSWORD=memledger-falkordb-password:latest"
fi

# One instance, always on: the per-tenant write lock is per process (TEN.md §5),
# and in embedded mode the data lives in that one instance.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated \
  --min-instances 1 --max-instances 1 --cpu 1 --memory 1Gi --timeout 300 --concurrency 40 \
  --set-env-vars "$ENV_VARS" --set-secrets "$SECRETS"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Deployed: $URL"
echo "Check it:  python scripts/smoke.py $URL --full"
