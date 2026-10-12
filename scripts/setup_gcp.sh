#!/usr/bin/env bash
# Enables the Google Cloud services ProductLoop uses. Run once: PROJECT_ID=your-project ./scripts/setup_gcp.sh
set -euo pipefail
: "${PROJECT_ID:?Set PROJECT_ID first}"
gcloud config set project "$PROJECT_ID"
gcloud services enable \
  aiplatform.googleapis.com bigquery.googleapis.com storage.googleapis.com \
  firestore.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
