#!/bin/bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-aegis-hackathon}"
REGION="${GCP_REGION:-us-central1}"
BACKEND_TIMEOUT="${BACKEND_TIMEOUT:-3600}"
BACKEND_SERVICE="aegis-backend"
FRONTEND_SERVICE="aegis-frontend"
BACKEND_IMAGE="gcr.io/$PROJECT_ID/$BACKEND_SERVICE"
FRONTEND_IMAGE="gcr.io/$PROJECT_ID/$FRONTEND_SERVICE"

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is required"
  exit 1
fi

echo "🚀 Deploying Aegis to Google Cloud Run..."
echo "   Project: $PROJECT_ID"
echo "   Region: $REGION"
echo "   Backend timeout: ${BACKEND_TIMEOUT}s"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  firebase.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"

echo "🔨 Building backend image..."
gcloud builds submit . \
  --tag "$BACKEND_IMAGE" \
  --project="$PROJECT_ID" \
  --file backend/Dockerfile \
  --quiet

echo "🚀 Deploying backend..."
BACKEND_URL=$(gcloud run deploy "$BACKEND_SERVICE" \
  --image "$BACKEND_IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout "$BACKEND_TIMEOUT" \
  --max-instances 5 \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --project="$PROJECT_ID" \
  --format='value(status.url)' \
  --quiet)

echo "✅ Backend deployed: $BACKEND_URL"

echo "🔨 Building frontend image..."
gcloud builds submit ./frontend \
  --tag "$FRONTEND_IMAGE" \
  --project="$PROJECT_ID" \
  --config ../infrastructure/cloudbuild.yaml \
  --substitutions "_FRONTEND_IMAGE=$FRONTEND_IMAGE,_VITE_API_URL=$BACKEND_URL,_VITE_WS_URL=${BACKEND_URL/https/ws}/ws/navigate" \
  --quiet

echo "🚀 Deploying frontend..."
FRONTEND_URL=$(gcloud run deploy "$FRONTEND_SERVICE" \
  --image "$FRONTEND_IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars "BACKEND_URL=${BACKEND_URL}" \
  --project="$PROJECT_ID" \
  --format='value(status.url)' \
  --quiet)

echo "✅ Frontend deployed: $FRONTEND_URL"

gcloud firestore databases create --location="$REGION" --project="$PROJECT_ID" 2>/dev/null || echo "(Firestore already exists)"

BUCKET="gs://${PROJECT_ID}-screenshots"
gsutil mb -l "$REGION" "$BUCKET" 2>/dev/null || echo "(Bucket already exists)"
gsutil cors set infrastructure/cors.json "$BUCKET" 2>/dev/null || true

echo "============================================"
echo "🎯 Aegis Deployment Complete"
echo "Frontend:  $FRONTEND_URL"
echo "Backend:   $BACKEND_URL"
echo "Storage:   $BUCKET"
echo "============================================"
