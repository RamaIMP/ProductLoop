# ProductLoop: Google Cloud setup for team members

You join the **shared Google Cloud project**. Do not create your own project or free trial: the shared one holds the credit, the enabled services and (later) the data.

| | |
|---|---|
| Project ID | `project-7eea7443-fac1-4364-9e6` |
| Region | `us-central1` |
| Dataset (BigQuery) | `productloop` (created later) |
| Gemini models in use | `gemini-2.5-flash` (extraction, chat), `gemini-2.5-flash-lite` (reasoning); embeddings `gemini-embedding-001` |

All data in this project is fictional.

---

## Part A: one-time steps by the project owner (already done unless marked)

| Step | Status |
|---|---|
| Google Cloud account, free trial (about ₹28,797 credit, 90 days, ends **7 Jan 2027**) | Done |
| Project created (ID above) | Done |
| Services enabled with `scripts/setup_gcp.sh`: Vertex AI, BigQuery, Cloud Storage, Firestore, Cloud Run, Cloud Build, Artifact Registry, Secret Manager | Done and checked |
| Two-step verification (MFA) turned on for the owner account | Owner to confirm |
| Budget alerts set (about ₹5,000 and ₹15,000) | Owner to confirm |
| **Add each teammate**: console.cloud.google.com, project selector, **IAM and admin, IAM, Grant access**, enter their Google account email, pick roles (below) | Per teammate |

**Roles to grant a teammate.** Quick option for the hackathon: **Editor**. Safer option (confirm names in the console): Vertex AI User, BigQuery Job User, BigQuery Data Editor, Storage Object Admin, Cloud Datastore User, Cloud Run Developer, Service Account User, Service Usage Consumer.

The teammate must also have two-step verification on their Google account (Google requires it for console access).

---

## Part B: steps for each teammate (about 20 minutes)

You need: a Google account the owner has added to the project, Homebrew, Git, Python 3.11 or newer.

**1. Install the Google Cloud CLI**
```
brew install --cask google-cloud-sdk
```
Open a new terminal afterwards so `gcloud` is on your PATH.

**2. Sign in (twice, both open a browser tab)**
```
gcloud auth login
gcloud auth application-default login
```
- The first is for the `gcloud` commands. The second is what our Python code uses.
- On the second one, **tick every permission box** on Google's consent screen. If you skip one you get: `cloud-platform scope is required but not consented`. Just run the command again.
- Use the same Google account the owner added.

**3. Point at the shared project**
```
gcloud config set project project-7eea7443-fac1-4364-9e6
gcloud auth application-default set-quota-project project-7eea7443-fac1-4364-9e6
```

**4. Check you can see it**
```
gcloud auth list                      # your account is marked active
gcloud config get-value project       # prints the project ID
gcloud services list --enabled | grep -E "aiplatform|bigquery|storage|firestore|run|cloudbuild"
```
You do **not** need to enable services; the owner already did. If the last command lists nothing or errors with "permission denied", ask the owner for a role.

**5. Get the code and set up Python**
```
git clone <repository URL from the owner>
cd productloop
python3 -m venv productLoop_env
source productLoop_env/bin/activate
pip install -r backend/requirements.txt
```
`backend/requirements.txt` pins `google-adk` to 2.x. Do not install an unpinned `google-adk`: pip can resolve to an old 1.x version. Run `pip check`; it should say "No broken requirements found."

**6. Settings**
You normally need no `.env`. The code reads settings from environment variables, then your own `.env` if you make one, then `backend/app/dev_defaults.json` (project ID, region, model names; nothing secret). To override something locally: `cp .env.template .env` and edit `.env`.

**7. First test: ask Gemini for one sentence**
```
python scripts/hello_gemini.py
```
Expected: a one-sentence reply. This proves your login, the project and Gemini access all work.

**8. Run the unit tests (no cloud needed)**
```
cd backend
python -m pytest tests/unit -q
```

---

## Rules for the whole team

- **Never create or download a service-account key file.** Everyone uses their own `gcloud` login; deployed code uses an attached service account.
- **Never commit `.env`, keys or tokens.** `.env` is in `.gitignore`. Real secrets go in Secret Manager.
- **Do not click Upgrade** on the trial banner, and do not turn on another billing account for this project.
- **Do not deploy a Vertex AI Vector Search index** (billed while it exists). Knowledge-base search uses BigQuery vector search.
- The credit is shared and ends 7 January 2027. Tell the owner if you run a large batch of Gemini calls (for example the full evaluation on 111 complaints).
- Stay in `us-central1` for every new resource.

---

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `gcloud: command not found` | Open a new terminal, or run `brew install --cask google-cloud-sdk` again |
| `cloud-platform scope is required but not consented` | Re-run `gcloud auth application-default login` and tick all boxes |
| `403`, `PERMISSION_DENIED`, `does not have permission` | You are missing a role. Send the owner the full error text |
| `Could not find default credentials` | Run `gcloud auth application-default login` |
| `quota project` warnings | Run the `set-quota-project` command in step 3 |
| `429` / `RESOURCE_EXHAUSTED` | Too many calls at once on a new account. Wait a minute, run fewer in parallel, or tell the owner |
| `404` model not found | Check the model name against `backend/app/dev_defaults.json`; models are listed with `client.models.list()` (see `scripts/hello_gemini.py` for the client setup) |
| pip dependency conflicts | Use a fresh virtual environment and `backend/requirements.txt` only |
| `ModuleNotFoundError` | The virtual environment is not active: `source productLoop_env/bin/activate` |

---

## Next steps after setup

Milestone M0 (setup) is finished when you can run the Gemini hello test. M1 is extraction against the taxonomy: see `docs/ProductLoop_Dev_Guide.pdf`, sections 6 and 8, and `backend/tests/eval/`.
