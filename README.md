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
| Operational state | SQLite locally; optional Firestore persistence with an ordered BigQuery outbox |
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
- API documentation endpoints are disabled. Application routes require a Firebase ID token by default.

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

The codebase defines **22 BigQuery tables**, grouped by purpose below. This is the schema inventory, not a claim that every table is populated in a new deployment.

### Consumer and incident lifecycle

| Table | Purpose |
| --- | --- |
| `registered_units` | Consumer-linked product registration and device metadata |
| `complaints` | Current complaint summary, symptoms, classification and status |
| `evidence` | One record per uploaded file, including storage and extracted findings |
| `complaint_events` | Incident activity and classification changes |

Complaint IDs connect incidents, evidence and events. Consumer and unit identifiers associate reports with their owner and registered device. The `evidence` table receives records only when a file is uploaded.

### Knowledge and configuration

| Table | Purpose |
| --- | --- |
| `taxonomy_symptoms` | Versioned symptom vocabulary, issue mappings, default severity and safety metadata |
| `kb_chunks` | Product knowledge passages, source metadata, retrieval tags and embedding vectors |
| `signal_config` | Analysis windows, volume thresholds, growth thresholds and safety/batch settings |
| `hypothesis_rules` | Rule-based hypothesis text, recommended actions and KB references for the SQL signal workflow |

### Batches, manufacturing and field evidence

| Table | Purpose |
| --- | --- |
| `batches` | Batch identifiers, production month, shipping start and shipment totals |
| `shipments_weekly` | Units shipped by batch, region and week; potential denominators for shipment-normalized rates |
| `production_batches` | Factory, production lines, production dates and units produced |
| `batch_lots` | Component/supplier lot traceability by batch, including tooling revisions and change notes |
| `change_records` | Manufacturing or engineering changes associated with batches |
| `end_of_line_tests` | Unit-level factory measurements and pass/fail results for acoustic, vibration, mechanical, thermal and battery checks |
| `service_repairs` | Field-service diagnoses, replaced parts and links to complaints, serial numbers and batches |
| `product_returns` | Returned products, reason codes, dispositions and complaint/batch links |

These tables provide context for manufacturing analysis. Their presence does not mean the current count-based dashboard reports shipment-normalized defect rates.

### Quality outputs and saved analysis

| Table | Purpose |
| --- | --- |
| `signals` | Computed quality-signal snapshots by product and issue type, including the structured signal payload |
| `investigations` | Investigation identifiers, status, actions and notes; schema support for an investigation workflow |
| `signal_analysis_scopes` | Requested analysis scopes, processing state and last-check information |
| `signal_analyses` | Versioned Gemini manufacturing interpretations with evidence snapshots, fingerprints, model and prompt metadata |
| `signal_sme_reviews` | SME verdicts and comments linked to an analysis version and hypothesis |
| `signal_analysis_monitor` | Source-change fingerprints and monitoring timestamps used by background checks |

The current manufacturing review uses `signal_analyses` and `signal_sme_reviews`; the `investigations` schema is not a claim of a complete investigation-management interface. Manufacturing hypotheses are suggestions for investigation, not confirmed root causes.

### Relationships and schema locations

- `consumer_id` and `unit_id` associate device registrations and complaints.
- `complaint_id` links complaints, uploaded evidence and lifecycle events; repair/return records can also reference it.
- `complaints.batch_reference` connects to manufacturing `batch_id` values, while serial numbers provide unit-level traceability.
- `scope_key` connects requested analysis scopes to saved analysis versions.
- `analysis_id` and `hypothesis_index` connect SME reviews to the exact saved hypothesis being reviewed.
- `chunk_id` identifies knowledge passages cited by retrieved guidance.

The 18 base table definitions are in [`bigquery/tables.sql`](bigquery/tables.sql). The four analysis-persistence table definitions are in [`backend/app/services/analysis_store.py`](backend/app/services/analysis_store.py). Apply the reviewed migrations in [`bigquery/migrations/`](bigquery/migrations/) when upgrading existing lifecycle schemas. The KB loader also defines additional retrieval/provenance fields in [`backend/app/services/load_kb_embeddings.py`](backend/app/services/load_kb_embeddings.py).

`bigquery/views/` is reserved for SQL views and currently has no view definitions. Factory test limits in `data/factory/spec_limits.json` are a configuration file, not a BigQuery table. Local SQLite `records` and `outbox` tables support operational persistence separately from this BigQuery inventory.

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

- Configure and live-test the implemented Google/Firebase sign-in and server-side ownership checks with two consumer accounts.
- Provision and test the explicit staff UID allowlist; a Google login alone must not grant dashboard access.
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

These include both implementation and deployment configuration:

1. **User identity:** Google/Firebase sign-in, backend token verification and ownership enforcement are implemented. Configure the provider and web apps, then verify a real browser login as described below. Legacy `user_id` request fields must equal the verified Firebase UID; forged IDs are rejected. See [Firebase ID-token verification](https://firebase.google.com/docs/auth/admin/verify-id-tokens).
2. **Staff access:** all dashboard/manufacturing routes and persistence status now require an explicitly approved Firebase UID. Configure the server-side allowlist and test both permitted and denied users. Staff review authorship is taken from the verified identity.
3. **Durable state:** enable and validate the optional Firestore adapter described below. Incidents, evidence metadata, registered units, events and the BigQuery outbox are supported. Existing SQLite data is not automatically migrated. BigQuery remains the analytics store; `SESSION_BACKEND=memory` is unrelated to this setting.
4. **Durable background work:** move uploads/outbox delivery and analysis checks into retryable workers or jobs. Use Cloud Scheduler to trigger an authenticated analysis job, with deduplication and meaningful-change checks. Do not depend on a web process staying alive between requests.
5. **Configuration:** replace hard-coded project references and add the actual frontend origins to CORS. Keep credentials out of frontend build variables.

Cloud Run's writable container filesystem is ephemeral, and the server must bind to `0.0.0.0` using the provided `PORT`. Restricting instance count does not make local SQLite durable. See the [Cloud Run runtime contract](https://docs.cloud.google.com/run/docs/container-contract).

#### Google sign-in and staff access

This code is secure-by-default but does not provision Firebase or change Cloud Run IAM. Keep the existing staging service private until the new image and authorization checks have been reviewed and tested.

1. In Firebase Console, select the **existing Google Cloud project** (add Firebase to that project if necessary; do not create a different project accidentally). In Authentication → Sign-in method, enable **Google**, choose a support email and save. Add each intended frontend hostname under Authentication → Settings → Authorized domains. Add `localhost` explicitly for local browser testing if it is absent. See [Google sign-in setup](https://firebase.google.com/docs/auth/web/google-signin).
2. Register a Firebase web app for each frontend (or use the same web app configuration for this POC). Copy the `apiKey`, `authDomain`, `projectId` and `appId` values into each frontend's `.env.local`, using its `.env.example`. These are public web configuration, **not** service-account credentials. `VITE_API_BASE_URL` must point to the intended API. Rebuild after configuration changes.
3. Configure backend `PRODUCTLOOP_AUTH_MODE=firebase`, `FIREBASE_PROJECT_ID` matching the web configuration, and `PRODUCTLOOP_CORS_ORIGINS` containing exact frontend origins (comma separated, no wildcard). Firebase Admin validates token signature, issuer, audience, expiry, revocation and disabled-account status. Only verified Google sign-ins are accepted. The runtime service account needs `firebaseauth.users.get` for the revocation/disabled-user lookup; the predefined **Firebase Authentication Viewer** role (`roles/firebaseauth.viewer`) includes it. A narrower custom role may be used. Do not grant Firebase Authentication Admin to the runtime. See [Firebase Authentication IAM](https://docs.cloud.google.com/iam/docs/roles-permissions/firebaseauth).
4. Sign in once, then obtain the intended staff account's UID from Firebase Authentication → Users. Set `PRODUCTLOOP_STAFF_UIDS` to only the approved UIDs (comma separated) on the backend. Empty means **no staff access**. Do not use emails, email domains, frontend variables or user-submitted roles. The dashboard also displays the signed-in UID when access is denied. Removing a UID requires deploying the updated server configuration and removing traffic from old revisions; disabling the Firebase user or revoking their sessions is checked on subsequent API requests.
5. Every API request sends a Firebase ID token in `Authorization: Bearer ...`. Both apps use tab-session persistence and clear application state on sign-out/account changes. Staff media is fetched with authorization into a temporary object URL, never via a bearer token in the URL. API responses are `private, no-store`. Ordinary consumers cannot read persistence diagnostics, dashboard data or manufacturing endpoints.

**Cloud Run IAM is a separate layer:** a Firebase ID token does not satisfy Cloud Run's IAM invoker check. For browser deployment, explicitly choose either an authenticated gateway/proxy that invokes the private service, or a Cloud Run endpoint reachable at the network layer with these backend Firebase checks enforcing application access. The latter is Google's documented end-user-auth pattern; it is **not** permission to expose the current old image. No access policy is changed by this code. See [Cloud Run end-user authentication](https://docs.cloud.google.com/run/docs/tutorials/identity-platform). Frontend deployment and this ingress decision remain separate steps.

For isolated local API fixtures only, explicitly set `PRODUCTLOOP_AUTH_MODE=development`, bind to `127.0.0.1`, use SQLite and disable BigQuery/analysis workers. Development mode is forbidden when `K_SERVICE` is set and rejects non-loopback clients. There is no automatic fallback if Firebase verification fails and no frontend demo-login bypass. Secure mode rejects Firebase Auth emulator configuration.

Existing `demo-ramachandra`/synthetic records are **not migrated or claimed by email**. New Firebase UIDs begin with their own records. Any future account-data migration needs an explicit ownership review.

Before publishing, verify in a real browser: Google sign-in/out; consumer A cannot read/update consumer B's reports or media; ordinary accounts get 403 on staff APIs; approved staff can view authorized evidence/export/review; disabled/revoked users are rejected; signing out clears cached data; both configured origins pass CORS. Automated tests mock token verification for route isolation and do not replace this live provider check. Rate limits, abuse protection and production monitoring are separate release-hardening work.

#### Optional Firestore operational persistence

Local development remains unchanged by default: `PRODUCTLOOP_STATE_BACKEND=sqlite`.
To test Firestore, first provision a Firestore Native-mode database in your intended Google Cloud project. Give the backend runtime identity the required Firestore access (typically `roles/datastore.user`); browser clients should not access these collections directly. Local testing uses Application Default Credentials, while Cloud Run uses its runtime service account. Never commit credential files.

Set these in the local ignored `.env`, or Cloud Run runtime environment, only when ready:

```dotenv
PRODUCTLOOP_STATE_BACKEND=firestore
GOOGLE_CLOUD_PROJECT=your-project-id
PRODUCTLOOP_FIRESTORE_DATABASE=(default)
PRODUCTLOOP_FIRESTORE_NAMESPACE=productloop-staging
```

Restart the backend after switching. The adapter uses
`productloop_state/{namespace}/{collection}/{document}` with collections
`registered_units`, `complaints`, `evidence`, `complaint_events`, `outbox`, and `metadata`.
The namespace parent is a path container; records live in its subcollections.
Media bytes remain in Cloud Storage. Each operation commits its structured records,
events and outbox entries together. Conflicting writes return HTTP 409 rather than
silently overwriting another change. Firestore errors do not silently fall back to SQLite.

This is a separate storage selection, **not a data migration**: existing local reports
and registrations remain in SQLite and will not appear in an empty Firestore namespace.
Switching back to `sqlite` restores access to the original local database. Do not run
local and staging writers against the same operational namespace/BigQuery destination.

For this stage, keep **one backend process and one active instance**. Background
uploads, BigQuery delivery and manufacturing checks still use in-process workers;
Firestore persistence alone does not make them safe for autoscaling or overlapping
deployment revisions. Stop the old writer before starting a replacement. Production
deployment still needs durable, coordinated jobs and authentication. Recent pending
media jobs are preserved on startup; jobs older than one hour are marked interrupted
on a later startup and require a new upload.

Run adapter regression tests without cloud writes:

```bash
cd backend
.venv/bin/python -m pytest tests/unit -q
```

An SDK integration test is also available when a local Firestore emulator is running:

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 .venv/bin/python -m pytest tests/integration/test_firestore_emulator.py -q
```

It uses an isolated emulator-only namespace. Without that environment variable the
test is skipped. A real staging smoke test is still required before deployment:
create a report, attach evidence, restart the backend, check report/ticket/appointment
retrieval, and verify pending BigQuery writes drain successfully.

### 4. Package and deploy the API to private staging

The repository includes a backend [`Dockerfile`](Dockerfile) and allowlist-based [`.dockerignore`](.dockerignore). It preserves the repository layout, installs the pinned backend dependencies and runs as a non-root user. Build from the repository root:

```bash
docker build -t productloop-api .
docker run --rm --name productloop-api -p 127.0.0.1:8080:8080 productloop-api
```

Check `http://localhost:8080/health`. This starts a health-checkable API, not a fully cloud-connected application. Supply your configuration with runtime environment variables and a secure credential mechanism for cloud calls. The image does not contain `.env` or credentials. On Cloud Run, use its runtime service account instead of baking credentials into the image.

Cloud persistence and in-process analysis are disabled by default in the image. Local SQLite uses `/tmp/productloop/lifecycle.sqlite3`; its contents remain ephemeral without external storage. Complete the deployment blockers above before public use. The container runs the equivalent of:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

The Docker build context excludes local state, secrets, Git metadata, media, test artifacts and frontend dependencies. A `.gcloudignore` still needs to be reviewed before source deployment: Docker exclusions do not independently control every cloud upload mechanism.

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

Both frontends include a tracked `.env.production` containing the public Firebase web configuration for `project-7eea7443-fac1-4364-9e6`. GitHub-based production builds therefore do not depend on a developer's ignored `.env.local`. The initial POC shares one Firebase web app between consumer and staff; backend UID authorization still controls staff access. Override these variables in the build environment when targeting another Firebase project.

The API URL is deliberately not pinned to the current IAM-private staging service: a browser Firebase token cannot invoke it directly. Supply `VITE_API_BASE_URL` for the approved gateway or auth-enabled API before publishing. This configuration change does not deploy either frontend or change Cloud Run access.

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

The intended delivery path is: **push → tests → approved build → deployment → smoke checks**. Docker packaging is included; Firebase and CI configuration still need to be added. Verify a real container build and deployment before release.
