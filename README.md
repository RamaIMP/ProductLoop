# ProductLoop

**Turn product complaints into consumer support and manufacturer quality insights.**

ProductLoop connects two experiences: a consumer reports an issue through text, voice, photos or video, while a manufacturer reviews structured complaints, emerging trends and evidence-backed manufacturing hypotheses.

The current implementation focuses on one product: the **X500 electric shaver**.

## Consumer experience

- Describe an issue in natural language, record a voice explanation, or upload photos, video and device audio.
- Extract symptoms and context with Gemini; derive issue type, severity and safety flags in code.
- Answer relevant follow-up questions and correct an earlier description when needed.
- Receive troubleshooting guidance grounded in the product knowledge base.
- Mark an issue resolved or raise a support ticket, request a callback or book a service appointment.
- Revisit submitted reports and registered product details.

Safety concerns bypass normal troubleshooting. A vague correction prompts clarification; an explicit correction can update the classification without discarding independent media evidence.

## Manufacturer experience

- Compare complaint counts across 7-, 30- and 90-day periods or a custom date range.
- See percentage changes, safety flags, issue categories and complaint trends.
- Drill into the complaints and evidence behind a signal.
- Export supported dashboard views as CSV for offline analysis.
- Review saved AI-generated manufacturing hypotheses and their supporting evidence.
- Record SME feedback: supported, not supported or needs more evidence.

The dashboard supports manual refresh and five-minute automatic refresh. Opening saved manufacturing analysis does not call Gemini; background processing checks for meaningful evidence changes before generating a new version.

## Architecture

```text
Consumer React app
  └─ FastAPI
      ├─ Gemini 2.5 Flash: conversation and media extraction
      ├─ Rule-based classification and safety checks
      ├─ RAG: query embedding → BigQuery vector search → retrieved chunks
      │   └─ Gemini 2.5 Flash-Lite: grounded text guidance
      ├─ Local incident state and persistence outbox → BigQuery
      └─ Media archive → private Cloud Storage, parallel to analysis

BigQuery complaints + manufacturing evidence
  ├─ Count-based quality signals → Manufacturer React dashboard
  └─ Background evidence checks → Gemini hypotheses → versioned saved analysis
                                                       └─ SME review
```

Previous media is represented in later conversation turns by extracted findings, rather than repeatedly sending the original file. Flash-Lite receives text for post-retrieval guidance; it is not a text-only-capability model.

## Technology stack

| Layer | Implementation |
| --- | --- |
| Consumer and manufacturer interfaces | React, Vite |
| Backend | Python 3.11+, FastAPI, Pydantic |
| Conversation and media | Gemini 2.5 Flash through Vertex AI |
| Post-retrieval answers | Gemini 2.5 Flash-Lite |
| Embeddings | `gemini-embedding-001` |
| Knowledge retrieval and analytics | BigQuery and BigQuery vector search |
| Media archive | Google Cloud Storage |
| Local operational state | SQLite with an ordered persistence outbox |
| Proposed deployment | Cloud Run for the API; Firebase Hosting for the frontends |

## Repository structure

```text
productloop/
├─ backend/
│  ├─ app/api/           # Consumer, lifecycle, dashboard and manufacturing endpoints
│  ├─ app/services/      # Gemini, retrieval, storage, persistence and analysis
│  ├─ app/models/        # Structured request and response schemas
│  ├─ app/rules/         # Classification and signal rules
│  ├─ app/guardrails/    # Safety, grounding and redaction
│  └─ tests/            # Automated tests and evaluation helpers
├─ frontend/
│  ├─ consumer/         # Consumer support application
│  └─ dashboard/        # Manufacturer quality dashboard
├─ data/                # Taxonomy, knowledge base and fixture data
├─ bigquery/            # Schemas, migrations, views, queries and loaders
├─ shared/              # Shared application assets and fixtures
├─ scripts/             # Setup and audit utilities
├─ docs/                # Design references and architecture documents
└─ deploy/              # Reserved for deployment configuration
```

## Run locally

### 1. Prerequisites

- Python 3.11 or newer.
- Node.js and npm compatible with the installed Vite version.
- Google Cloud CLI and access to a project with the required Vertex AI, BigQuery and Cloud Storage resources for cloud-backed functionality.

### 2. Configure the environment

From the repository root:

```bash
cp .env.example .env
```

Fill in your own project, dataset and bucket values. Set the model names explicitly:

```dotenv
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
BQ_DATASET=productloop
GCS_MEDIA_BUCKET=your-private-media-bucket
GEMINI_MODEL_EXTRACT=gemini-2.5-flash
GEMINI_MODEL_CHAT=gemini-2.5-flash
GEMINI_MODEL_REASON=gemini-2.5-flash-lite
EMBEDDING_MODEL=gemini-embedding-001
PRODUCTLOOP_BIGQUERY_ENABLED=0
PRODUCTLOOP_ANALYSIS_WORKER_ENABLED=0
```

Authenticate locally using Application Default Credentials:

```bash
gcloud auth application-default login
```

Keep BigQuery persistence and background analysis disabled until their tables and permissions are configured. Disabling persistence does **not** disable live RAG or dashboard reads: those still require BigQuery resources. For local retrieval fixtures, set `PRODUCTLOOP_RAG_MODE=mock`; conversation and media analysis still require Gemini access.

**Important:** some setup/load scripts and development defaults still reference the original project. Review and replace those targets before running any cloud setup or data-loading command. Startup alone does not provision the cloud resources. Never commit `.env`, credentials or service-account keys.

### 3. Start the backend

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- API health: <http://127.0.0.1:8000/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>

### 4. Start the consumer app

In another terminal, from the repository root:

```bash
cd frontend/consumer
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open <http://localhost:5173>.

### 5. Start the manufacturer dashboard

In another terminal, from the repository root:

```bash
cd frontend/dashboard
npm install
npm run dev
```

Open <http://localhost:5174>.

Both frontends use the local API by default. Configure `VITE_API_BASE_URL` when using another API address; update the backend CORS configuration for any new frontend origins.

## Data model

The four core input tables are:

| Table | Purpose |
| --- | --- |
| `registered_units` | Consumer-linked product registration and device metadata |
| `complaints` | Current complaint summary, symptoms, classification and status |
| `evidence` | One record per uploaded file, including storage and extracted findings |
| `complaint_events` | Incident activity and classification changes |

Complaint IDs connect incidents, evidence and events. Consumer and unit identifiers associate reports with their owner and registered device. The `evidence` table receives records only when a file is uploaded.

`kb_chunks` holds knowledge-base content, retrieval metadata and embedding vectors. Separate configuration, signal and manufacturing tables support quality analysis. Manufacturing hypotheses are suggestions for investigation, not confirmed root causes.

## Tests and builds

Backend, from `backend/` with the virtual environment activated:

```bash
python -m pytest tests/unit -q
```

Run these commands in **each** frontend directory:

```bash
node --test src/*.test.js
npm run build
```

Unit tests isolate local state and mock external dependencies. Live audit scripts can call paid cloud APIs; some also write data. Inspect each script before running it. Passing unit tests does not certify every live-model answer or browser interaction.

Binary media fixtures and PDF/presentation artifacts are not included in this source distribution. Supply local media fixtures before running media audit scripts; their filenames and expected metadata are described in `data/test_media/`.

## Current scope and deployment readiness

This is a hackathon proof of concept. X500 knowledge and seeded manufacturing/service data are illustrative, not official product documentation. Callback and appointment workflows record application state; they are not connected to a real scheduling or contact-centre system.

Before public deployment:

- Replace the fixed development identity with authenticated users and enforce ownership server-side.
- Add manufacturer/staff authentication and authorization.
- Replace or adapt local SQLite state and in-process workers for the chosen hosting architecture.
- Configure production CORS, secrets, retention, monitoring and cloud permissions.
- Review the knowledge base, safety handling and live end-to-end journeys with appropriate domain experts.
- Audit repository contents for private documents, media, identifiers and test artifacts before publishing.

Cloud Run and Firebase Hosting are the intended deployment targets, not a claim that deployment has already been completed.

## Deployment guide: GitHub → Google Cloud

**Status: deployment plan, not a one-command deployment of the current code.** The steps below distinguish required code changes from cloud configuration. No infrastructure is created by reading this guide.

### 1. Publish the source repository

Create a GitHub repository and push the reviewed source. A public repository does not require a public database, storage bucket or backend.

Before the first commit, review `git status` and the files being staged. Exclude `.env`, credentials, `.runtime/`, virtual environments, `node_modules/`, build outputs, uploaded media and generated test reports. Review documents and seed data individually before publishing. Do not assume the current `.gitignore` covers every private artifact.

GitHub stores the source; it does not automatically deploy the application. First perform a manual staging deployment, then connect a deployment workflow.

### 2. Prepare the Google Cloud project

Use your own project, enable billing and configure budget alerts. In a terminal with the Google Cloud CLI installed:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com storage.googleapis.com
```

Use a dedicated runtime service account for the API. Grant only the permissions its operations need: Vertex AI access, BigQuery query jobs and access to the relevant datasets, and object access on the private media bucket. Keep build/deployment permissions separate from runtime permissions. Do not download a service-account key into the repository.

Provision and validate the BigQuery schemas, KB embeddings, private bucket and manufacturing tables against the intended project. Inspect every setup script first: several still have original-project targets. Existing cloud data is not included automatically in a GitHub push.

### 3. Complete the deployment blockers

These are implementation tasks, not environment-variable switches:

1. **User identity:** add Firebase Authentication to the consumer app. Send the signed-in user's ID token with requests and verify it in FastAPI. Derive ownership from the verified user ID, not the submitted `user_id`. See [Firebase ID-token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens).
2. **Staff access:** protect dashboard and manufacturing endpoints with staff authorization. Replace the local-only IP guard with explicit authorization; do not simply remove it.
3. **Durable state:** migrate incidents, evidence metadata, report lookup and the outbox from local SQLite/in-memory state to a managed operational store such as Firestore or Cloud SQL. BigQuery remains the analytics store. `SESSION_BACKEND=memory` does not implement this migration.
4. **Durable background work:** move uploads/outbox delivery and analysis checks into retryable workers or jobs. Use Cloud Scheduler to trigger an authenticated analysis job, with deduplication and meaningful-change checks. Do not depend on a web process staying alive between requests.
5. **Configuration:** replace hard-coded project references and add the actual frontend origins to CORS. Keep credentials out of frontend build variables.

Cloud Run's writable container filesystem is ephemeral, and the server must bind to `0.0.0.0` using the provided `PORT`. Restricting instance count does not make local SQLite durable. See the [Cloud Run runtime contract](https://docs.cloud.google.com/run/docs/container-contract).

### 4. Package and deploy the API to private staging

After completing the blockers, add a reviewed Dockerfile at the repository root. Preserve the repository layout: backend code also references resources outside `backend/`. Install backend dependencies during the build and run the following command from the container's backend working directory:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

Provide a `.dockerignore` and `.gcloudignore` before uploading a build context. Exclude local state, secrets, Git metadata, media, test artifacts and frontend dependencies. Include the runtime data/shared resources the backend actually needs. A `.gitignore` alone is not a complete container-packaging review.

From the repository root, this command is an example **after that packaging exists**:

```bash
gcloud run deploy productloop-api \
  --source . \
  --region us-central1 \
  --service-account productloop-api@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```

Cloud Run source deployment builds the application through Cloud Build. Configure the deployer and build service-account permissions described in [Google's source deployment guide](https://docs.cloud.google.com/run/docs/deploying-source-code).

In **Cloud Run → productloop-api → Edit and deploy new revision**, configure the non-secret environment values from the local setup section for the target project. Set live RAG explicitly. Enable BigQuery persistence only once the durable outbox integration is ready; keep the in-process analysis worker disabled when using a separate job. Use Secret Manager references for any actual secrets.

Record the service URL. Test `/health` and protected API operations using an authorized staging client. A private Cloud Run service requires Cloud Run invocation authentication; Firebase user tokens alone do not satisfy that IAM layer. Before browser launch, choose either an authenticated gateway or a publicly invokable API that verifies application tokens and staff roles on every protected endpoint. Do not expose the current unauthenticated API.

### 5. Configure the two Firebase Hosting sites

In the Firebase console, add Firebase to the same Google Cloud project. Install the Firebase CLI, sign in, and select that project. From the repository root:

```bash
npm install -g firebase-tools
firebase login
firebase use --add
firebase hosting:sites:create YOUR_CONSUMER_SITE_ID
firebase hosting:sites:create YOUR_DASHBOARD_SITE_ID
firebase target:apply hosting consumer YOUR_CONSUMER_SITE_ID
firebase target:apply hosting dashboard YOUR_DASHBOARD_SITE_ID
```

Site IDs must be available. Add this `firebase.json` at the repository root:

```json
{
  "hosting": [
    {
      "target": "consumer",
      "public": "frontend/consumer/dist",
      "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
      "rewrites": [{ "source": "**", "destination": "/index.html" }]
    },
    {
      "target": "dashboard",
      "public": "frontend/dashboard/dist",
      "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
      "rewrites": [{ "source": "**", "destination": "/index.html" }]
    }
  ]
}
```

Hosting targets keep the two frontend deployments separate. See [Firebase deploy targets](https://firebase.google.com/docs/cli/targets) and [multiple Hosting sites](https://firebase.google.com/docs/hosting/multisites).

### 6. Build and publish the frontends

Run the following in each frontend directory, substituting the deployed API or gateway URL:

```bash
npm install
VITE_API_BASE_URL=https://YOUR_API_HOST npm run build
```

Vite embeds this URL at build time. Changing the backend address later requires rebuilding. Never place secrets in `VITE_` variables.

After authentication and API access have been verified, deploy from the repository root:

```bash
firebase deploy --only hosting:consumer,hosting:dashboard
```

The sites will be available at `https://YOUR_CONSUMER_SITE_ID.web.app` and `https://YOUR_DASHBOARD_SITE_ID.web.app`. Add the chosen origins to backend CORS and the authentication configuration. Hosting a dashboard page does not secure its API or its data.

### 7. Verify the deployed journey

- Sign in as two different consumers; verify their reports cannot be accessed across accounts.
- Upload media; verify extraction, private storage and evidence linkage.
- Submit a report; verify the same complaint ID in the operational store and BigQuery.
- Exercise grounded guidance, safety escalation, explicit corrections, resolution and service booking.
- Verify the dashboard's date filters, complaint drill-down, exports and manual/automatic refresh.
- Verify manufacturing results are reused when evidence is unchanged and versioned when material evidence changes.
- Restart or replace the API instance; confirm state and pending work survive.
- Review logs for errors and ensure tokens, raw media and sensitive complaint content are not logged unnecessarily.

### 8. Automate deployment from GitHub

Once manual staging deployment passes, add workflows that run tests, build and deploy the API, then build and deploy both Hosting targets. Commit reviewed dependency lockfiles and use reproducible installs in CI. Keep production deployment behind an approval step and restrict deployment to the intended branch.

For Google Cloud authentication from GitHub Actions, prefer repository/branch-restricted Workload Identity Federation rather than a long-lived JSON key. See [Google's deployment-pipeline federation guide](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

The intended delivery path is: **push → tests → approved build → deployment → smoke checks**. Docker, Firebase and CI configuration described here still need to be added and verified; this README does not create them.
