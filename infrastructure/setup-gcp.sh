#!/bin/bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-aegis-hackathon}"
REGION="${GCP_REGION:-us-central1}"

gcloud config set project "$PROJECT_ID"

echo "⚠️ Ensure billing is enabled: https://console.cloud.google.com/billing"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  firebase.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"

SA_NAME="aegis-app"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME" \
  --display-name="Aegis App Service Account" \
  --project="$PROJECT_ID" 2>/dev/null || true

for role in roles/datastore.user roles/storage.objectAdmin roles/run.invoker; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --quiet >/dev/null
done

echo "✅ GCP setup complete for ${PROJECT_ID} (${REGION})"
