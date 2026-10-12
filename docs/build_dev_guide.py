"""Content of docs/ProductLoop_Dev_Guide.pdf (pages as HTML). Rendered by docs/dev_guide_render.py: python3 docs/dev_guide_render.py
Numbers (rows, symptoms, signals) are read from the data files so the guide cannot drift from the data."""
import json, re, html, subprocess, statistics as S, collections as C, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA, BQ, SEED, FAC = ROOT / "data", ROOT / "bigquery", ROOT / "bigquery" / "seed", ROOT / "data" / "factory"
J = lambda p: json.load(open(p)); NJ = lambda n: [json.loads(l) for l in open(SEED / f"{n}.ndjson")]
tax = J(DATA / "taxonomy_v2.json"); kb = J(DATA / "x500_rag_knowledge_base_v2.json")["chunks"]; comp = J(DATA / "x500_complaints_v2.json")["complaints"]
batches = J(DATA / "batches.json")["batches"]; signals = NJ("signals_preview"); rules = NJ("hypothesis_rules"); cfg = NJ("signal_config")[0]
fac = {n: J(FAC / f"{n}.json") for n in ["production_batches", "batch_lots", "change_records", "end_of_line_tests", "service_repairs", "returns"]}
reg = J(DATA / "registered_units.json"); ship = NJ("shipments_weekly"); evid = NJ("evidence")
sql = re.sub(r"--[^\n]*", "", open(BQ / "tables.sql").read())
e = html.escape
def split_top(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch in "<(") - (ch in ">)")
        if ch == "," and depth == 0: out.append(cur.strip()); cur = ""
        else: cur += ch
    return out + ([cur.strip()] if cur.strip() else [])
schemas = {}
for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \(", sql):
    i, depth = m.end(), 1; j = i
    while depth: depth += {"(": 1, ")": -1}.get(sql[j], 0); j += 1
    schemas[m.group(1)] = [re.match(r"(\w+)\s+(.+?)(\s+NOT NULL)?$", " ".join(p.split())).groups()[:2] for p in split_top(sql[i:j - 1])]
SIG_COLS = ["computed_at TIMESTAMP", "issue_type STRING", "window_start DATE", "window_end DATE", "current_count INT64", "prior_count INT64", "change_pct FLOAT64",
 "rate_current_per_1000 FLOAT64", "rate_prior_per_1000 FLOAT64", "rate_change_pct FLOAT64", "safety_count INT64", "persists_share FLOAT64", "top_batch STRING",
 "top_batch_events INT64", "batch_event_share FLOAT64", "batch_unit_share FLOAT64", "batch_multiple FLOAT64", "top_symptoms ARRAY<STRUCT<symptom,n>>",
 "evidence_count INT64", "status STRING", "priority STRING", "reason STRING", "rule_id STRING", "hypothesis STRING", "actions ARRAY<STRING>"]

def tbl(head, rows, w=None, cls=""):
    g = "".join(f'<col style="width:{x}">' for x in w) if w else ""
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><colgroup>{g}</colgroup><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'
ul = lambda items, cls="": f'<ul class="{cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"
ol = lambda items: "<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"
c_ = lambda t: f"<code>{e(t)}</code>"
box = lambda t, cls="": f'<div class="box {cls}">{t}</div>'
PAGES = []   # (toc label or None, html)
def page(toc, body): PAGES.append((toc, body))
pct = lambda v: f"{v:.0f}%"

# ============================== PAGE 1: cover ==============================
page(None, f"""
<div class="cover"><div class="kicker">ProductLoop</div><h1>End-to-End Development Guide</h1>
<div class="tagline">Part 1: consumer complaint and guidance &nbsp;·&nbsp; Part 2: quality signal detection<br>Tech stack &nbsp;·&nbsp; Data and how it is used &nbsp;·&nbsp; Folder structure &nbsp;·&nbsp; Work plan</div>
{tbl(["Version","Date","Status","Audience","Scope"],[["1.0","8 October 2026","Design complete, build starting","Development team","X500 electric shaver prototype, fictional data, India and UK"]],["9%","15%","26%","17%","33%"],"meta")}
</div>
<h2 class="nb">Contents</h2>%%TOC%%
<h2>Ground rules for the whole team</h2>
{ol([
 "<b>One source of truth for categories.</b> <code>data/taxonomy_v2.json</code> defines every issue type and symptom. Prompts, models, rules, SQL reference data and UI labels are generated from it. Never hard-code a category.",
 "<b>The model extracts; code decides.</b> Gemini returns symptoms and context. Issue type, severity and the safety flag are derived by plain Python rules, so they can never disagree.",
 "<b>Safety is deterministic.</b> Stop-use rules run before the model on every message. A model answer can never override them.",
 "<b>Gemini reads each media file once.</b> After extraction the chat agent sees only the extracted record, never the audio, video or photo again.",
 "<b>Answers come from the knowledge base.</b> Guidance must cite the chunks it was given, or it is rejected.",
 "<b>Phase 1 hypotheses are rules, not an LLM.</b> The investigation assistant (LLM) is Phase 2.",
 "<b>No secrets in Git.</b> Use <code>.env</code> locally and Secret Manager in the cloud. All data in this project is fictional."])}
""")

# ============================== PAGE 2: product and scope ==============================
page("1. Product and scope", f"""
<h2 class="nb">1. Product and scope</h2>
<p><b>The problem.</b> Manufacturers learn about field problems when returns spike, which is too late. Customer-experience platforms say customers are unhappy but not why a device fails. Quality-management systems track known defects but miss emerging field signals. Nothing bridges consumer evidence and the manufacturer's investigation.</p>
<p><b>The idea.</b> One consumer interaction produces two outcomes: (1) immediate, <i>grounded</i> guidance for the consumer from the product knowledge base, and (2) a structured, evidence-backed quality signal for the manufacturer. The loop closes when the signal leads to an investigation and a better product.</p>
{tbl(["","Part 1: consumer side","Part 2: quality-management side"],[
 ["Users","Owners of an X500 shaver, on a phone","Quality engineers and managers, in a browser"],
 ["Goal","Report a problem in a chat; get safe, sourced next steps; see the outcome","See emerging problems early, with evidence, batch and a hypothesis; start an investigation"],
 ["Main capabilities","Multimodal intake (text, voice, photo, video), follow-up questions, confirm card with consent, grounded guidance, stop-use safety override, my reports","Signal detection every 15 minutes, trend and baseline comparison, batch concentration, safety banner, evidence clips, rule-based hypothesis, investigation page (Phase 2)"],
 ["AI used","Gemini (extraction, guidance), Google embeddings (search)","None in Phase 1 (SQL and rules); LLM investigation assistant in Phase 2"],
 ["Key tables","complaints, evidence, registered_units, kb_chunks","signals, plus complaints, shipments_weekly, factory tables, investigations"]],["15%","42.5%","42.5%"])}
<h2>Prototype scope</h2>
<div class="cols2"><div><b>In scope</b>{ul(["One product: the X500 electric shaver","Two regions: India (main) and the UK","Text, voice, photo and video intake","Gemini extraction against a fixed taxonomy","Grounded guidance with sources (RAG)","Safety override for stop-use conditions","Complaint store, trend and signal detection in BigQuery","Dashboard with evidence, batch view and rule-based hypothesis","Everything running on Google Cloud"])}</div>
<div><b>Phase 2 and later</b>{ul(["LLM investigation assistant and actions","Factory, supplier and service evidence page in the dashboard","Guided, standardised evidence capture","Acoustic fingerprint and video condition checks","Real serial or QR linkage and registration","Privacy-preserving batch correlation","Anomaly detection by supplier or product age","QMS, PLM and ERP integration; multi-product, multi-region"])}</div></div>
<h2>What a successful demo shows</h2>
{ol(["A consumer reports a noisy, vibrating shaver with an audio clip, answers two questions, confirms, and gets sourced steps within seconds.",
"Typing \"it smells burnt when charging\" triggers the stop-use screen at once, with no troubleshooting steps.",
"The dashboard shows three emerging signals (noise and vibration, head fitment, heat and safety), each tied to a batch, with evidence clips and a hypothesis.",
"The same consumer report is traceable from chat to BigQuery row to dashboard signal.",
"The whole system is deployed on Google Cloud, not just run on a laptop."])}
""")

# ============================== PAGE 3: architecture ==============================
page("2. Architecture", """
<h2 class="nb">2. Architecture</h2>
<div class="arch">
<div class="lane"><div class="lt">Apps &nbsp;(React + Vite, Firebase Hosting)</div><div class="row"><div class="b c1"><b>Consumer app</b>Home · Chat · Confirm card · Guidance · My reports</div><div class="b c2"><b>Quality dashboard</b>Overview · Signal detail · Evidence · Investigation (Phase 2)</div></div></div>
<div class="ar">&#8597; HTTPS (JSON)</div>
<div class="lane"><div class="lt">Backend API &nbsp;(Python + FastAPI, Cloud Run)</div><div class="row">
<div class="b c1 big"><b>Part 1 engine</b>Chat gateway with <strong>safety rules</strong> &rarr; <strong>ADK chat agent</strong> (Gemini) &rarr; tools: <i>save_complaint, search_kb, my_reports</i>. Media extraction runs <b>before</b> the agent (one Gemini call).<br>Guardrails: user scoping, taxonomy validator, cite-or-reject, redaction</div>
<div class="b c2 big"><b>Part 2 engine</b>Read-only dashboard endpoints (signals, anonymised views, evidence links) and investigation endpoints<br>No model calls in Phase 1</div></div></div>
<div class="ar">&#8597; Google Cloud client libraries</div>
<div class="lane"><div class="lt">Google Cloud services</div><div class="row">
<div class="b g"><b>Gemini + embeddings</b>Vertex AI</div><div class="b"><b>Cloud Storage</b>audio, video, photos</div><div class="b"><b>Firestore</b>chat sessions</div>
<div class="b c3"><b>BigQuery</b>complaints · evidence · kb_chunks (vectors) · batches · shipments · factory tables · signals · investigations</div>
<div class="b"><b>Scheduled query</b>every 15 min &rarr; signals</div></div></div>
</div>
<h2>End-to-end flow</h2>
<div class="cols2"><div><b>Part 1: consumer</b>"""+ol([
 "User taps <b>Report a problem</b> and lands on the chat page.",
 "On <b>attach</b>, the app uploads the file straight to Cloud Storage with a signed URL.",
 "Each message goes to the API. The gateway runs <b>stop-use rules</b> on the text and loads the session.",
 "If media is attached, <code>extract_from_media</code> makes <b>one</b> Gemini call and stores the extracted record in the session. The agent only sees a text note.",
 "The ADK agent asks at most 3 to 4 follow-ups for missing context. Code derives issue type, severity and safety flag.",
 "The <b>confirm card</b> (edit, add comment, consent) triggers <code>save_complaint</code>: rows in <code>complaints</code> and <code>evidence</code>.",
 "<code>search_kb</code> filters by tags then runs <code>VECTOR_SEARCH</code> on <code>kb_chunks</code>; safety chunks are added for high severity. Gemini writes guidance citing chunk IDs; uncited answers are rejected.",
 "The user answers <b>did it help?</b>; the outcome is saved on the complaint."])+"""</div>
<div><b>Part 2: quality</b>"""+ol([
 "A BigQuery <b>scheduled query</b> runs every 15 minutes and rewrites the <code>signals</code> table from complaints, weekly shipments, thresholds and hypothesis rules.",
 "The dashboard API reads <code>signals</code> and <b>anonymised views</b> only. Consumer ID, serial number and raw text are never exposed.",
 "The React dashboard shows tiles, the signal list, trend and batch charts, the safety banner and evidence clips (through short-lived signed links).",
 "In <b>Phase 2</b>, the investigation page joins factory tables (lots, changes, end-of-line tests, repairs, returns) for the batch. <b>Open investigation</b> writes to <code>investigations</code>; an LLM assistant can later draft actions."])+"""</div></div>
""")

# ============================== PAGE 4: tech stack ==============================
page("3. Tech stack", f"""
<h2 class="nb">3. Tech stack</h2>
{tbl(["Layer","Choice","Notes"],[
 ["Language","Python 3.11 or newer","ADK installed cleanly on Python 3.14 in our test. Without the ADK 2.x constraint, pip resolved ADK 1.14 alongside the other libraries, so keep the constraint and commit a lock file (<code>pip freeze &gt; backend/requirements.lock.txt</code>)."],
 ["Backend","FastAPI + Uvicorn on Cloud Run","Scales to zero; deploy from source (<code>gcloud run deploy --source</code>), no Docker needed"],
 ["Agent framework","Google ADK 2.x (<code>google-adk&gt;=2,&lt;3</code>; 2.11 tested)","LlmAgent with Python-function tools, <code>before_model_callback</code> and <code>before_tool_callback</code> for guardrails, Runner + session service"],
 ["LLM","Gemini through Vertex AI","Set <code>GOOGLE_GENAI_USE_VERTEXAI=TRUE</code>. Model names are configuration; pick current ones from the Vertex AI model list"],
 ["Embeddings","Google embedding model","Task types: document for chunks, query for searches. Same model and vector length everywhere"],
 ["Database","BigQuery","One dataset, 17 tables. Unqualified table names; the client sets the default dataset"],
 ["Vector search","BigQuery <code>VECTOR_SEARCH</code> on <code>kb_chunks</code>","Cosine distance; no index needed for 41 chunks. Text, tags and vectors live in one row"],
 ["Media","Cloud Storage (private bucket)","Signed upload URLs at attach time; signed read URLs for the dashboard"],
 ["Sessions","ADK in-memory (dev), Firestore adapter (deploy)","Cloud Run can restart at any time, so deployed sessions need a persistent store. ADK ships in-memory, SQL and Vertex-managed services; Firestore needs a small custom service"],
 ["Frontend","React + Vite (TypeScript recommended)","Two apps: consumer (mobile-first) and dashboard. Charts follow the visual rules in the mockups"],
 ["Hosting","Firebase Hosting","Both web apps"],
 ["Repo and deploy","GitHub + Cloud Build","Push to <code>main</code> redeploys the backend; <code>firebase deploy</code> for the apps"],
 ["Secrets and identity","Secret Manager, service accounts","Least-privilege roles (see section 9)"],
 ["Validation and tests","Pydantic, pytest","Models generated from the taxonomy; evaluation harness (section 8)"]],["15%","27%","58%"])}
<h2>Decisions already made, and why</h2>
{tbl(["Decision","Reason"],[
 ["ADK from the start","Chosen by the team: agent structure, callbacks for guardrails, built-in test UI, and it matches the Google story. Keep the tool functions plain so they can be tested without ADK"],
 ["BigQuery vector search instead of Vertex AI Vector Search or Vertex AI Search","No extra service to deploy or pay for while idle; one table holds text, tags and vectors; filters are plain <code>WHERE</code> clauses. Vertex AI Vector Search remains a scale-up path for many products"],
 ["SQL and rules for signals and hypotheses in Phase 1","Deterministic, auditable and testable; no model cost or latency on the quality side"],
 ["Severity and safety derived in code","Removes model inconsistency; safety recall can be tested exactly"],
 ["Gemini reads media once","Avoids re-sending audio or video on every chat turn (cost and delay)"],
 ["Closed taxonomy with an <code>other_or_unclear</code> bucket","Grouping becomes a <code>GROUP BY</code>; growth in the unclear bucket is itself a signal"]],["32%","68%"])}
<h2>Not in the stack</h2>
<p>Chroma, MySQL, local models, Vertex AI Vector Search, Vertex AI Search, Model Armor and Sensitive Data Protection (named as next-step options for production hardening).</p>
""")

# ============================== PAGE 5: folder structure ==============================
page("4. Folder structure", """
<h2 class="nb">4. Folder structure</h2>
<pre class="tree">productloop/                         repository root (git, branch: main)
├── README.md   .gitignore   .env.template
├── backend/                         Python: FastAPI + ADK  (Cloud Run)
│   ├── pyproject.toml               dependencies
│   ├── app/
│   │   ├── main.py                  FastAPI app, /health
│   │   ├── config.py                reads environment variables
│   │   ├── api/                     chat.py · reports.py · dashboard.py        endpoints
│   │   ├── agents/                  chat_agent.py · instructions.py            ADK agent + prompt text
│   │   ├── tools/                   extract.py · save_complaint.py · search_kb.py · my_reports.py
│   │   ├── guardrails/              safety_rules.py · grounding.py · redaction.py
│   │   ├── rules/                   derive.py (issue type, severity, safety) · signals.py
│   │   ├── services/                gemini.py · embeddings.py · bigquery.py · storage.py · sessions.py
│   │   └── models/                  taxonomy.py  (Pydantic, generated from taxonomy_v2.json)
│   └── tests/                       unit/  ·  eval/  (extraction, retrieval, signals oracle)
├── frontend/                        React + Vite  (Firebase Hosting)
│   ├── consumer/                    Home · Chat · My reports
│   ├── dashboard/                   Overview · Signal detail · Evidence · Investigation
│   └── shared/                      shared types, styles, taxonomy labels
├── data/                            all fictional data + generators
│   ├── taxonomy_v2.json / .md       single source of truth
│   ├── x500_rag_knowledge_base_v2.json     41 chunks            kb_conflicts_log.md
│   ├── x500_complaints_v2.json / .csv      111 rows             registered_units.json   batches.json
│   ├── factory/                     production, lots, changes, end-of-line tests, repairs, returns
│   ├── test_media/                  6 test files + answer_key.json + recording_script.md
│   └── generate_*.py  validate_*.py  build_kb.py  kb_part*.py      reproducible builders and checks
├── bigquery/
│   ├── tables.sql                   16 table definitions (signals is created by the scheduled query)
│   ├── views/                       anonymised and trend views              (to write)
│   ├── scheduled/                   signals.sql, the 15-minute job          (to write)
│   ├── seed_src/                    signal_config.json · hypothesis_rules.json
│   ├── seed/                        load-ready NDJSON, one file per table (generated)
│   └── build_seed.py  preview_signals.py  build_viewer.py  load_data.py (to write)
├── scripts/                         setup_gcp.sh (enables the Google APIs)
├── deploy/                          cloudbuild.yaml, firebase.json         (to write)
└── docs/                            this guide, architecture, mockups, database-viewer.html</pre>
<h2>Who works where</h2>
"""+tbl(["Area","Folders","Typical work"],[
 ["AI and backend","backend/app/agents, tools, guardrails, rules, services, api","ADK agent, extraction, safety rules, derive rules, search tool, API endpoints"],
 ["Data and BigQuery","bigquery/, data/","Tables, load script, embeddings, views, signals query, checks against the Python oracle"],
 ["Consumer app","frontend/consumer","Home, chat, confirm card, guidance, my reports, upload on attach"],
 ["Dashboard","frontend/dashboard","Tiles, signal list, charts, evidence, investigation page"],
 ["Shared","docs/, deploy/, scripts/, backend/tests","Setup, CI, deployment, evaluation harness, demo script"]],["18%","38%","44%"])+"""
<p class="small">Build scripts are idempotent. <code>python3 data/generate_dataset.py</code>, <code>data/generate_factory_data.py</code>, <code>data/build_kb.py</code> and <code>bigquery/build_seed.py</code> recreate the data deterministically; each has a matching <code>validate_*.py</code> check.</p>
""")

WHERE_FROM = f"""<h3>Where each dataset comes from in real life</h3>
{tbl(["In this project","In a real deployment"],[
 ["complaints, evidence","Written live by the consumer app when a report is confirmed"],
 ["registered_units","Product registration or QR / serial capture"],
 ["batches, shipments_weekly, production_batches, batch_lots, change_records","ERP, MES and procurement systems"],
 ["end_of_line_tests","Factory test stations"],["service_repairs, product_returns","Service-centre and returns systems"],
 ["kb_chunks","Product manuals and service guides, chunked and embedded by the loader"]],["50%","50%"],"tight")}"""
# ============================== PAGE 6: data inventory + storyline ==============================
n_comp = sum(c["counts_as_complaint"] for c in comp); n_q = len(comp) - n_comp
dates = sorted(c["timestamp"][:10] for c in comp)
units_in, units_uk = sum(b["units_shipped_india"] for b in batches), sum(b["units_shipped_uk"] for b in batches)
page("5. Data", f"""
<h2 class="nb">5. Data and how it is used</h2>
<p>Everything is fictional and reproducible. Scripts regenerate every file with fixed seeds; each has a validation script.</p>
<h3>5.1 Dataset inventory</h3>
{tbl(["Dataset","File(s)","Size","Used by"],[
 ["Taxonomy v2","data/taxonomy_v2.json, .md",f"{len(tax['issue_types'])} issue types, {len(tax['symptoms'])} symptoms","Pydantic models, Gemini prompt and schema, derive rules, taxonomy_symptoms table, UI labels"],
 ["Source documents","Data_synthetic/*.md","5 files","Original text. Conflicts resolved with <b>the safety document winning</b> (kb_conflicts_log.md)"],
 ["Knowledge base v2","data/x500_rag_knowledge_base_v2.json",f"{len(kb)} chunks","kb_chunks table; search_kb tool (RAG)"],
 ["Complaints v2","data/x500_complaints_v2.json, .csv",f"{len(comp)} rows ({n_comp} complaints, {n_q} questions), {dates[0]} to {dates[-1]}","complaints table (seed); ground-truth labels for the evaluation harness"],
 ["Registered units","data/registered_units.json",f"{len(reg)} units","serial number to batch lookup; consumer IDs for my reports"],
 ["Batches and shipping","data/batches.json; bigquery/seed/shipments_weekly",f"{len(batches)} batches ({units_in:,} India + {units_uk:,} UK units); {len(ship)} weekly rows","Rates per 1,000 units; batch share of units"],
 ["Factory evidence","data/factory/*.json, .csv",f"production {len(fac['production_batches'])}, lots {len(fac['batch_lots'])}, changes {len(fac['change_records'])}, end-of-line tests {len(fac['end_of_line_tests'])}, repairs {len(fac['service_repairs'])}, returns {len(fac['returns'])}","Phase 2 investigation page"],
 ["Test media","data/test_media/","6 files + answer_key.json","Extraction and retrieval tests; recording_script.md covers real recordings"],
 ["Settings","bigquery/seed_src/",f"signal_config (1 row), hypothesis_rules ({len(rules)} rules)","Signals job thresholds and hypothesis text"],
 ["Load-ready seed","bigquery/seed/*.ndjson","one file per table + signals_preview","Loader input; signals_preview is the oracle for the SQL"]],["15%","26%","26%","33%"])}
<h3>5.2 The demo storyline in numbers</h3>
<p>Windows: current {signals[0]['window_start']} to {signals[0]['window_end']} (30 days) against the 30 days before. Counts exclude questions. <b>Per-1,000-unit rates</b> use units shipped to date, so growth in the installed base is not mistaken for a quality problem.</p>
{tbl(["Issue type","Prior","Now","Count","Rate","Safe","Top batch","Batch x","Status","Priority"],[
 [s["issue_type"].replace("_"," "),s["prior_count"],s["current_count"],(f"{s['change_pct']:+.0f}%" if s["change_pct"] is not None else "n/a"),(f"{s['rate_change_pct']:+.0f}%" if s["rate_change_pct"] is not None else "n/a"),s["safety_count"],s["top_batch"] or "-",(f"{s['batch_multiple']:.1f}x" if s["batch_multiple"] else "-"),
  f'<span class="tag {"t-hi" if s["status"]=="emerging" else "t-lo"}">{s["status"].replace("_"," ")}</span>',s["priority"]] for s in sorted(signals,key=lambda s:-s["current_count"])],
 ["19%","6%","6%","8%","8%","6%","15%","8%","14%","10%"],"tight")}
<p class="small">Count and Rate = change vs the prior 30 days (rate per 1,000 units shipped). Safe = safety-flagged. Batch x = top batch share of events divided by its share of units. Source: bigquery/seed/signals_preview.ndjson, computed in Python from the seed files (<code>bigquery/preview_signals.py</code>). The BigQuery scheduled query must reproduce these rows.</p>
<div class="box"><b>Designed so no single category dominates.</b> Three categories rise (noise and vibration, head fitment, heat and safety), each with its own batch and its own factory cause; four stay flat. Control batches look normal, and one red herring (a blade supplier change in batch B-2026-06-C with normal blade tests) should <i>not</i> be blamed by an investigation.</div>

""")

# ============================== PAGE 7: taxonomy ==============================
sev_ct = C.Counter(v["default_severity"] for v in tax["symptoms"].values()); stop = [k for k, v in tax["symptoms"].items() if v["safety"]]
page("5.3 Taxonomy", f"""
<h2 class="nb">5.3 Taxonomy and derivation rules</h2>
<p>The controlled vocabulary lives in <code>data/taxonomy_v2.json</code>. <b>Symptoms are one global list</b>: any symptom can appear with any issue type (for example <code>increased_noise</code> together with <code>excessive_heat</code>). Each symptom has a home issue type, a default severity, a stop-use flag and a flag for whether it counts as a complaint.</p>
{tbl(["Issue type","Symptoms","Meaning"],[[f"<code>{k}</code>",len(v["symptoms"]),v["description"]] for k,v in tax["issue_types"].items()],["30%","10%","60%"],"tight")}
<p class="small">Default severities: low {sev_ct['low']}, medium {sev_ct['medium']}, high {sev_ct['high']}. Stop-use symptoms ({len(stop)}): {", ".join(c_(x) for x in stop)}. Full list in Appendix A.</p>
<h3>What Gemini returns, and what code derives</h3>
<div class="cols2"><div><b>Gemini returns (schema-constrained)</b><pre>{{
  "product_model": "X500",
  "user_intent": "report_problem",
  "symptoms": ["rattling_sound",
               "increased_vibration"],
  "context": {{
    "onset": "this_week",
    "persists_after_cleaning": "yes",
    "during_charging": false
  }},
  "confidence": 0.88
}}</pre></div>
<div><b>Code derives (never the model)</b><pre>{{
  "issue_type": "noise_and_vibration",
  "severity":   "medium",
  "safety_flag": false
}}
user_intent: report_problem | ask_question
onset: today | this_week | longer | unknown
persists_after_cleaning:
  yes | no | not_tried | not_applicable
during_charging: true | false | null</pre></div></div>
<h3>Derivation rules (implemented in backend/app/rules/derive.py)</h3>
{ol([
 "<b>issue_type</b>: take the symptoms present; choose the issue type of the highest-severity symptom; break ties with the priority order "+", ".join(c_(x) for x in tax["derivation_rules"]["issue_type_priority"])+".",
 "<b>severity</b> starts as the highest default severity among the symptoms.",
 "If <code>persists_after_cleaning</code> is <code>yes</code> and severity is low (and the issue type is not cleaning or unclear), severity becomes <b>medium</b>.",
 "If the issue type is head fitment, a loose, wobbling or non-seating head is reported, and the problem persists after cleaning and refitting, severity becomes <b>high</b> (the safety guide says a head that cannot be secured must not be used).",
 "If <code>user_intent</code> is <code>ask_question</code>, severity is low unless a safety symptom is present.",
 "<b>safety_flag</b> is true when severity is high (stop-use conditions from <code>03_safety_escalation.md</code>)."])}
<h3>Extraction rules and confidence</h3>
{ul(["Return only symptoms from the list; never invent one. Select every symptom the user states or the evidence clearly shows.",
 "Use <code>increased_noise</code> only when no specific sound is named; otherwise use the specific sound symptom.",
 "<b>Heat wording:</b> set <code>excessive_heat</code> only for \"hot\" or \"too hot\". \"Warm\" is normal per the operating specs, so ask one follow-up instead.",
 f"Confidence below <b>{tax['confidence_rules']['ask_follow_up_below']}</b>: ask one follow-up question. Still below <b>{tax['confidence_rules']['use_other_or_unclear_below']}</b>: use <code>other_or_unclear</code> symptoms. Do not guess.",
 "Do not diagnose internal faults. A possible cause may appear only in the grounded answer, and only if a retrieved passage supports it."])}
""")

# ============================== PAGE 8: BigQuery data model ==============================
NOTE_ROWS = {
 "complaints": ("One row per confirmed report; private columns stay out of the dashboard", "App (save_complaint); seed", "Signals job, views, my_reports"),
 "evidence": ("Links to audio, video, photo in Cloud Storage; consent flag", "App on confirm; seed", "Evidence views, signals (counts)"),
 "registered_units": ("Serial number to batch, region, purchase date, consumer", "Registration (seed)", "save_complaint, my_reports"),
 "kb_chunks": ("Knowledge passages with tags and embedding", "Loader (embeds)", "search_kb tool"),
 "taxonomy_symptoms": ("Vocabulary as data: issue type, severity, stop-use, counts-as-complaint", "Loader from taxonomy_v2.json", "Signals job, views, labels"),
 "signal_config": ("One row of thresholds, pinned as-of date for the demo", "Loader", "Signals job"),
 "hypothesis_rules": ("Rule-based hypothesis text and suggested checks", "Loader", "Signals job"),
 "signals": ("One row per issue type: counts, rates, status, priority, batch, hypothesis", "Scheduled query (every 15 min)", "Dashboard API"),
 "investigations": ("Investigation records and action checklist", "Dashboard API", "Dashboard API"),
 "batches": ("Production batches and units shipped by region", "ERP feed (seed)", "Signals job, views"),
 "shipments_weekly": ("Units shipped per batch, region, week", "ERP / sales feed (seed)", "Signals job (rates)"),
 "production_batches": ("Plant, lines, production dates, units produced", "MES (seed)", "Investigation page"),
 "batch_lots": ("One supplier lot per component per batch, with change notes", "Procurement (seed)", "Investigation page"),
 "change_records": ("Approved supplier, tooling and test-limit changes", "Change control (seed)", "Investigation page"),
 "end_of_line_tests": ("Sampled unit tests: sound, vibration, torque, temperature, burn-in", "Test stations (seed)", "Investigation page"),
 "service_repairs": ("Repair diagnosis, part replaced, link to complaint", "Service systems (seed)", "Investigation page"),
 "product_returns": ("Returns by batch and reason, link to complaint", "Returns system (seed)", "Investigation page")}
rowcount = {"complaints": len(comp), "evidence": len(evid), "registered_units": len(reg), "kb_chunks": len(kb), "taxonomy_symptoms": len(tax["symptoms"]), "signal_config": 1, "hypothesis_rules": len(rules),
 "signals": len(signals), "investigations": 0, "batches": len(batches), "shipments_weekly": len(ship), "production_batches": len(fac["production_batches"]), "batch_lots": len(fac["batch_lots"]),
 "change_records": len(fac["change_records"]), "end_of_line_tests": len(fac["end_of_line_tests"]), "service_repairs": len(fac["service_repairs"]), "product_returns": len(fac["returns"])}
page("5.4 BigQuery tables", f"""
<h2 class="nb">5.4 BigQuery data model: 17 tables</h2>
<p>One dataset (<code>productloop</code>). Table names are unqualified in the SQL; the client sets the default dataset, so the same files run in any environment. Definitions: <code>bigquery/tables.sql</code> (16 tables). The 17th, <code>signals</code>, is created by the scheduled query with <code>CREATE OR REPLACE</code>. Open <code>docs/database-viewer.html</code> to browse every table, its schema and its rows.</p>
{tbl(["Table","Rows now","What it holds","Written by","Read by"],[[f"<code>{k}</code>",rowcount[k],v[0],v[1],v[2]] for k,v in NOTE_ROWS.items()],["23%","5%","33%","19%","20%"],"tight")}
<h3>Key relationships</h3>
{ul(["<code>complaints.batch_reference</code> = <code>batches.batch_id</code>; every factory table also carries <code>batch_id</code>.",
 "<code>complaints.serial_number</code> = <code>registered_units.serial_number</code>, which gives the batch and purchase date so the consumer never types it.",
 "<code>evidence</code>, <code>service_repairs</code> and <code>product_returns</code> carry <code>complaint_id</code> (nullable for repairs and returns without a logged complaint).",
 "<code>signals.rule_id</code> = <code>hypothesis_rules.rule_id</code>; <code>signals.issue_type</code> comes from <code>taxonomy_symptoms.issue_type</code>, so categories are never hard-coded in SQL."])}
<h3>Storage choices</h3>
{ul(["<code>complaints</code> is partitioned by <code>DATE(created_at)</code> and clustered by <code>issue_type, batch_reference</code>.",
 "Arrays and structs are used where natural: <code>symptoms ARRAY&lt;STRING&gt;</code>, <code>context STRUCT&lt;onset, persists_after_cleaning, during_charging&gt;</code>; query them with <code>UNNEST</code>.",
 "Large files never go in tables: <code>evidence.gcs_uri</code> holds a Cloud Storage link. <code>evidence.demo_file</code> points at a local test file for development before the bucket is populated.",
 "<code>kb_chunks.embedding</code> is <code>ARRAY&lt;FLOAT64&gt;</code>, filled by the loader; <code>embedding_model</code> records which model produced it. Never mix models in one table."])}
""")

# ============================== PAGE 9: data usage ==============================
ex = next(c for c in comp if c["issue_type"] == "noise_and_vibration" and c["batch_reference"] == "B-2026-07-A" and "audio" in c["input_type"] and c["timestamp"] >= "2026-09-07")
exu = next(r for r in reg if r["complaint_id"] == ex["complaint_id"])
M = {"complaints": ("W save_complaint · R my_reports", "W seed", "R (view)", "R (view)"), "evidence": ("W on confirm", "W seed", "R counts", "R (view)"),
 "registered_units": ("R serial lookup", "W seed", "", ""), "kb_chunks": ("R search_kb", "W + embeddings", "", ""),
 "taxonomy_symptoms": ("", "W from JSON", "R", "R labels"), "signal_config": ("", "W", "R", ""), "hypothesis_rules": ("", "W", "R", ""),
 "signals": ("", "", "W (replace)", "R"), "investigations": ("", "", "", "R / W"), "batches": ("", "W seed", "R", "R (view)"),
 "shipments_weekly": ("", "W seed", "R", "R (view)"), "production_batches, batch_lots, change_records, end_of_line_tests, service_repairs, product_returns": ("", "W seed", "", "R (investigation page)")}
page("5.5 Data usage", f"""
<h2 class="nb">5.5 Data usage: who reads and writes what</h2>
{tbl(["Table","Consumer API and agent","Loader","Signals job","Dashboard API"],[[f"<code>{k}</code>" if "," not in k else "<code>production_batches</code>, <code>batch_lots</code>, <code>change_records</code>, <code>end_of_line_tests</code>, <code>service_repairs</code>, <code>product_returns</code>",*v] for k,v in M.items()],["32%","22%","14%","14%","18%"],"tight")}
<p class="small">W = writes, R = reads. "view" means through an anonymised view. The evaluation harness reads the JSON files, not BigQuery, so tests do not depend on cloud state.</p>
<h3>Privacy split inside <code>complaints</code></h3>
{tbl(["Private (never leaves the consumer side)","Shared with the quality side, through views only"],[
 ["<code>consumer_id</code>, <code>serial_number</code>, <code>raw_complaint</code>, <code>updated_at</code>","<code>complaint_id</code>, date, <code>batch_reference</code>, <code>region</code>, <code>product_model</code>, <code>symptoms</code>, <code>context</code>, <code>issue_type</code>, <code>severity</code>, <code>safety_flag</code>, <code>guidance_outcome</code>, <code>language</code>, and <code>redacted_complaint</code> (as the text shown)"]],["38%","62%"],"tight")}
{ul(["Rows reach the quality side only when <code>consent_share</code> is true and <code>counts_as_complaint</code> is true (questions are excluded).","Evidence reaches the dashboard only when both the evidence row and its complaint have consent. Files are opened through short-lived signed links, never public URLs.","Redaction removes phone numbers and email addresses when <code>redacted_complaint</code> is created."])}
<h3>One report, end to end (real row from the data)</h3>
{tbl(["Step","What exists"],[
 ["1. Consumer says",f"\"{e(ex['raw_complaint'])}\" with an attached {e('/'.join(t for t in ex['input_type'] if t != 'text'))} clip ({ex['complaint_id']}, {ex['timestamp'][:10]})"],
 ["2. Gemini extracts",f"symptoms {e(', '.join(ex['symptoms']))}; persists_after_cleaning = {ex['context']['persists_after_cleaning']}; confidence {ex['confidence']}"],
 ["3. Code derives",f"issue_type {ex['issue_type']}, severity {ex['severity']}, safety_flag {str(ex['safety_flag']).lower()}"],
 ["4. Stored",f"<code>complaints</code> row (batch {exu['batch_id']} from serial {exu['serial_number']}; consumer {exu['consumer_id']}, private) and <code>evidence</code> row with the Cloud Storage link"],
 ["5. Counted","In the current window for noise and vibration (one of 27), 78% of which are batch B-2026-07-A"],
 ["6. Shown","Signal row, trend chart, batch chart, evidence table (consent permitting), and the rule-based hypothesis"]],["20%","80%"],"tight")}
{WHERE_FROM}
""")

# ============================== PAGE 10: Part 1 journey ==============================
page("6. Part 1: consumer side", f"""
<h2 class="nb">6. Part 1: consumer side</h2>
<p>The consumer app is a chat-based <b>complaint box</b>, not a general assistant. The home screen has one main action; the chat page collects the report, asks only for missing facts, and ends with sourced guidance. Product questions are answered from the knowledge base as <code>ask_question</code> and are not counted as complaints. Working prototypes: <code>docs/consumer-app-prototype.html</code> (clickable) and <code>docs/consumer-chat-preview.html</code>.</p>
<h3>6.1 Screens</h3>
{tbl(["Screen","What the user sees","Data and calls"],[
 ["Home","Greeting, registered X500 card, <b>Report a problem</b>, my reports with status, service-centre shortcut","GET reports; registered_units; complaints (own rows)"],
 ["Chat: intake","Messages, quick-reply buttons, attach buttons (voice, photo, video, sound), progress bar","Upload on attach; POST chat message"],
 ["Chat: confirm card","What we understood (product, symptoms, started, after cleaning, evidence); Edit, Add a comment, <b>Looks right</b>; anonymous-sharing consent","Draft in session state; nothing saved yet"],
 ["Chat: guidance","Sourced steps (source chips), warning line, \"That fixed it\" / \"Still not fixed\", service centre and talk to a person","complaints + evidence written; search_kb; outcome saved"],
 ["Safety override","Red \"Stop using it now\" card, service-centre and support buttons, high-priority note","Stop-use rules only; no model answer, no troubleshooting"],
 ["My reports","List with status badges (awaiting feedback, resolved); a report can receive later comments","complaints for this consumer"]],["16%","50%","34%"],"tight")}
<h3>6.2 Chat flow (state machine)</h3>
{tbl(["State","What happens","Next"],[
 ["AWAIT_DESCRIPTION","Greeting. User types or attaches a file. Attach starts an upload immediately.","SAFETY_CHECK"],
 ["SAFETY_CHECK","Runs on <b>every</b> message: stop-use rules on the text (burn, smoke, spark, shock, melt, too hot, detached head, liquid in port…). Match: show the safety card, mark high priority, offer service centre; the user may add details.","SAFETY branch or EXTRACT"],
 ["EXTRACT","Text, and media <b>once</b>, go to Gemini: symptoms, context, confidence. Code derives issue type, severity, safety flag. Confidence below 0.6 asks one clarifying question.","FOLLOW_UP"],
 ["FOLLOW_UP","Ask only missing context: onset; persists after cleaning (when relevant); during charging (heat and charging). At most 3 to 4 questions, with quick replies; typed answers are accepted.","CONFIRM"],
 ["CONFIRM","Card with Edit, Add a comment, <b>Looks right</b> and the consent line. Edit returns to AWAIT_DESCRIPTION; a comment is stored on the draft.","SAVE_AND_GUIDE"],
 ["SAVE_AND_GUIDE","Write <code>complaints</code> and <code>evidence</code>; <code>search_kb</code>; Gemini writes sourced guidance; cite-or-reject; for a head still loose or other stop-use outcomes show the service path.","OUTCOME"],
 ["OUTCOME","\"That fixed it\" or \"Still not fixed\" is saved on the complaint. Later messages update the same report; they never create a second one.","DONE"],
 ["DONE","Return to Home; My reports shows the status.",""]],["19%","66%","15%"],"tight")}
<div class="box warn"><b>Stop-use rules are code, not prompt text.</b> They run before the model and cannot be overridden by it. They also cover typed text only; audio and video are covered by the <code>safety_flag</code> derived from Gemini's extracted symptoms, which triggers the same screen.</div>
""")

# ============================== PAGE 11: ADK agent, extraction, media, guardrails ==============================
page("6.3 Agent and guardrails", f"""
<h2 class="nb">6.3 ADK agent, extraction and guardrails</h2>
{tbl(["Piece","Design"],[
 ["<code>chat_agent</code> (ADK LlmAgent)","Model from config; instruction built from the taxonomy (<code>agents/instructions.py</code>); tools below; callbacks below. It writes follow-up questions and the guidance wording. It does not decide safety, severity or what is saved."],
 ["Tools (plain Python functions)","<code>save_complaint(draft)</code> writes the confirmed report; <code>search_kb(issue_type, symptoms, severity, query)</code> returns chunks; <code>my_reports()</code> lists the caller's own reports. Each has a docstring ADK turns into the tool description, and can be unit-tested without ADK."],
 ["<code>before_model_callback</code>","Runs the stop-use rules on the latest user text. On a match it returns the fixed safety response and the model is never called."],
 ["<code>before_tool_callback</code>","Forces <code>user_id</code> from session state into every tool call and rejects mismatches, so one user can never read another's reports."],
 ["Output checks","Pydantic validates extraction output against the taxonomy (unknown symptom: reject and retry once). The grounding check requires cited chunk IDs to be among those retrieved."],
 ["Session state","<code>user_id, report_id, stage, draft{symptoms, context, confidence, attachments, comment}, media_summary, questions_asked, consent</code>. In-memory in development; Firestore-backed session service when deployed."],
 ["Runner and API","Each chat request: load session, run the safety check, run media extraction if a file arrived, call the Runner, map the events to API messages (text, quick replies, cards)."]],["24%","76%"],"tight")}
<h3>Who decides what</h3>
{tbl(["Gemini","Code and rules","Data"],[
 ["Reads text, audio, video, photo; returns symptoms, context, confidence; words the follow-up questions; writes the guidance from the passages given","Stop-use detection; issue type, severity, safety flag; which context is still missing; retrieval filters; cite-or-reject; redaction; consent; saving","Taxonomy (allowed values), knowledge-base chunks, product registration"]],["38%","38%","24%"],"tight")}
<h3>Media is read once</h3>
{ol(["On attach, the app uploads the file directly to Cloud Storage with a signed URL and keeps the <code>gs://</code> link.","The message sent to the API carries the link and any typed text, never the bytes.","<code>extract_from_media(gcs_uri)</code> runs <b>outside</b> the agent loop: one Gemini call reads the file with the taxonomy schema and returns symptoms, context, confidence and a short description of what the evidence shows.","The result is stored in session state (<code>media_summary</code>, draft). The agent receives only a text note such as \"user attached audio; extracted: rattling_sound\".","Later turns and the guidance step use the stored record. The file is not sent again, so cost and delay do not grow with the length of the chat."])}
<h3>Guardrails</h3>
{tbl(["Guardrail","Where","Cost"],[
 ["Stop-use rules (deterministic)","<code>before_model_callback</code>; derived safety flag for media","None"],
 ["User-scoped tools","<code>before_tool_callback</code> plus tool context","None"],
 ["Taxonomy validator, cite-or-reject grounding check","Pydantic models; post-processing of the model's answer","None"],
 ["Redaction of phone numbers and emails","When creating <code>redacted_complaint</code>","None (local rules)"],
 ["Gemini safety settings and system instructions","Part of each model call","No separate charge"],
 ["Least-privilege service account; escaped model text in the UI","IAM; React renders text safely (avoid <code>dangerouslySetInnerHTML</code>)","None"],
 ["Next step, not in Phase 1: Model Armor, Sensitive Data Protection, Gemini-as-judge plugin","ADK plugins","Paid or extra model calls; prices not verified"]],["46%","36%","18%"],"tight")}
""")

# ============================== PAGE 12: RAG + API ==============================
page("6.4 RAG and API", f"""
<h2 class="nb">6.4 Retrieval (RAG) and API</h2>
<p><code>kb_chunks</code> holds the {len(kb)} knowledge passages: text, tags (<code>issue_types</code>, <code>symptoms</code>, <code>severity_applicability</code>, <code>document_type</code>, <code>safety_critical</code>), and the <code>embedding</code> vector. Retrieval happens after the user confirms the report, and for later product questions.</p>
{ol(["<b>Build the query</b> from the structured record, not the raw message, for example \"X500 rattling sound increased vibration troubleshooting\". Embed it with the same model, query task type.",
 "<b>Filter</b> the table: product X500, chunk tags match the derived issue type (or \"general\"), severity in <code>severity_applicability</code>.",
 "<b>Rank</b> the remaining rows with <code>VECTOR_SEARCH</code>, cosine distance, top 5.",
 "<b>Safety rule:</b> if severity is high, always add the five <code>safety_escalation</code> chunks, whatever the similarity says.",
 "<b>Minimum match:</b> if the closest chunk is too far away (threshold to tune), do not guess; say so and offer the service centre.",
 "<b>Generate:</b> Gemini writes steps from the chunks only and must cite <code>chunk_id</code>s.",
 "<b>Cite or reject:</b> if the answer cites nothing, or an ID that was not retrieved, discard it and use the safe fallback message."])}
<pre>SELECT base.chunk_id, base.title, base.content, distance
FROM VECTOR_SEARCH(
  (SELECT * FROM kb_chunks WHERE product_model = 'X500' AND @issue_type IN UNNEST(issue_types)),
  'embedding', (SELECT @query_embedding AS embedding),
  top_k =&gt; 5, distance_type =&gt; 'COSINE')</pre>
<p class="small">Pattern only: confirm the exact syntax and filtering behaviour against the current BigQuery documentation when implementing. Embeddings: one chunk per request when using Gemini embedding models; record <code>embedding_model</code>; after loading, check that all {len(kb)} rows have a vector of the same length.</p>
<h3>Draft API (to confirm in milestone 0)</h3>
{tbl(["Method and path","Purpose","Request → response"],[
 ["POST /api/v1/uploads/sign","Signed upload URL, called when a file is attached","filename, mime type → upload_url, gcs_uri"],
 ["POST /api/v1/chat/messages","Send a message or a quick-reply choice","report_id?, text?, attachments[], choice? → messages[] (text, quick replies, cards), stage"],
 ["POST /api/v1/reports/{id}/confirm","Confirm the card","comment?, consent → guidance (steps, sources), report status"],
 ["POST /api/v1/reports/{id}/outcome","Did it help?","helped | not_helped → ok"],
 ["GET /api/v1/reports, /reports/{id}","My reports and one report","→ list, detail (own rows only)"],
 ["GET /api/v1/service-centres","Nearby centres (mock data in the prototype)","lat, lon → list"],
 ["GET /api/v1/dashboard/summary","Tiles","→ counts, safety, open signals, evidence"],
 ["GET /api/v1/dashboard/signals","Signal list","→ rows from <code>signals</code>"],
 ["GET /api/v1/dashboard/signals/{issue_type}","Detail for one signal","→ signal, weekly series, batch events, symptoms"],
 ["GET /api/v1/dashboard/evidence?issue_type=","Evidence table","→ items with short-lived signed read links"],
 ["GET /api/v1/dashboard/safety","Safety banner","→ safety-flagged complaints (anonymised)"],
 ["GET /api/v1/dashboard/signals/{issue_type}/factory","Investigation data (Phase 2)","→ lots, changes, end-of-line summary, repairs, returns"],
 ["POST / GET / PATCH /api/v1/investigations","Open, list, update an investigation","issue_type, actions → investigation"]],["33%","27%","40%"],"tight")}
<p class="small">Authentication for the prototype is an open decision (see section 11). Until it is made, send a demo user ID in a header and treat it as trusted.</p>
""")

# ============================== PAGE 13: Part 2 dashboard + signals job ==============================
page("7. Part 2: quality side", f"""
<h2 class="nb">7. Part 2: quality-management side</h2>
<p>The dashboard is a browser app for quality engineers. Phase 1 uses <b>SQL and rules only</b>: no model is called. Reference mockup: <code>docs/quality-dashboard.html</code> (its numbers pre-date Data v2; use the values in section 5.2). Charts follow one visual system: a single accent colour, one axis per chart, thin marks, status colours always with an icon and a label, a table view for every chart, hover tooltips and a light/dark theme.</p>
<h3>7.1 Dashboard elements and their data</h3>
{tbl(["Element","Content","Source"],[
 ["Safety banner","Safety-flagged complaints needing review, with batch","anonymised complaints view"],
 ["Tiles","Complaints in 30 days (with change), open signals, safety-flagged, evidence items; weekly sparkline","<code>signals</code> and weekly counts view"],
 ["Signal list","One row per issue type: change, event count, status chip (emerging, watching, stable, low volume)","<code>signals</code>"],
 ["Signal header and headline figure","Count change <b>and</b> rate change per 1,000 units; cluster and confidence notes; top symptoms with counts","<code>signals</code>"],
 ["Hypothesis and suggested checks","Rule-selected text and a checklist; buttons <b>Open investigation</b> and <b>Export evidence pack</b>","<code>signals</code>, <code>investigations</code>"],
 ["Trend chart","Events per week against the prior 30-day average, with prior and current windows marked","weekly counts view"],
 ["Batch chart","Events by production batch against the batch's share of units shipped; the callout shows the multiple and warns for small samples","batch events view"],
 ["Evidence table","Anonymised items (type, date, what the consumer said, severity) with Review; short-lived signed links","evidence view"],
 ["Investigation page (Phase 2)","For the top batch versus the others: end-of-line results, supplier lots with change notes, change records, repairs by diagnosis, returns","factory tables"]],["22%","50%","28%"],"tight")}
<h3>7.2 The signals job (<code>bigquery/scheduled/signals.sql</code>, every 15 minutes)</h3>
<p>One scheduled query rewrites <code>signals</code> with <code>CREATE OR REPLACE TABLE</code>. Categories are taken from <code>taxonomy_symptoms</code>, so a category with no complaints still gets a row.</p>
{ol([f"<b>Windows</b> from <code>signal_config</code>: as-of date ({cfg['as_of_date']} for the demo; NULL means today), window {cfg['window_days']} days. Current = the last 30 days; prior = the 30 days before.",
 "<b>Counts</b> per issue type from the counted-complaints view (consented complaints only, questions excluded): current, prior, safety-flagged, and the share of reporters who say the problem persists after cleaning (yes / (yes + no)).",
 "<b>Rates</b>: units shipped to date from <code>shipments_weekly</code> at the end of each window; rate = events / units × 1,000; rate change = current rate / prior rate − 1. Growth tests use the <b>rate</b> change, so a larger installed base is not mistaken for a worse product.",
 "<b>Batch concentration</b>: the batch with most current events; its share of events; its share of units shipped; <b>multiple</b> = event share / unit share. Computed only with at least "+str(cfg['min_batch_events'])+" events; otherwise null (small sample).",
 "<b>Top symptoms</b> (5), <b>evidence count</b>, then status, priority and hypothesis as below."])}
{tbl(["Setting","Value","Meaning"],[
 ["min_events / min_events_safety",f"{cfg['min_events']} / {cfg['min_events_safety']}","Events needed to be emerging; the lower number applies when at least "+f"{int(cfg['safety_share_min']*100)}% of events are safety-flagged"],
 ["growth_pct",f"{cfg['growth_pct']:.0f}%","Rate change needed to be emerging (or no events in the prior window)"],
 ["watch_min_events / watch_growth_pct",f"{cfg['watch_min_events']} / {cfg['watch_growth_pct']:.0f}%","Thresholds for watching; below the minimum is low volume"],
 ["batch_multiple_flag",f"{cfg['batch_multiple_flag']:.1f}x","Batch concentration that raises priority"],
 ["min_batch_events",f"{cfg['min_batch_events']}","Minimum sample for a batch multiple"]],["32%","14%","54%"],"tight")}
<div class="cols2"><div><b>Status</b>{ul(["<b>emerging</b>: events ≥ minimum and (no prior events or rate change ≥ growth)","<b>watching</b>: any safety-flagged event, or events ≥ watch minimum and rate change ≥ watch growth","<b>low volume</b>: events below the watch minimum","<b>stable</b>: everything else"])}</div>
<div><b>Priority and hypothesis</b>{ul(["<b>high</b>: emerging and (any safety-flagged event or batch multiple ≥ flag)","<b>medium</b>: other emerging or watching","<b>low</b>: the rest","Hypothesis: best-matching rule by specificity (next page); placeholders filled from the row"])}</div></div>
<p class="small">The thresholds were calibrated on the demo data (growth 75% so head fitment, +85% per 1,000 units, qualifies). Treat them as prototype settings, not statistical guarantees. BigQuery notes: <code>QUALIFY</code> needs a <code>WHERE</code>, <code>GROUP BY</code> or <code>HAVING</code> in the same query; use <code>ROW_NUMBER</code> instead of <code>LIMIT</code> inside <code>ARRAY_AGG</code> so the query can also be tested in DuckDB.</p>
""")

# ============================== PAGE 14: signals output + rules + views ==============================
def cond(r):
    c = []
    if r["min_batch_multiple"]: c.append(f"batch multiple ≥ {r['min_batch_multiple']:g}")
    if r["min_persists_share"]: c.append(f"persists share ≥ {int(r['min_persists_share']*100)}%")
    return "; ".join(c) or "any"
page("7.3 Signals output and rules", f"""
<h2 class="nb">7.3 Expected output, hypothesis rules and views</h2>
<p>The scheduled query must reproduce these rows for the demo data (<code>bigquery/preview_signals.py</code> is the oracle; counts must match exactly, rates within 0.1). Hypothesis and actions are stored on each row.</p>
{tbl(["Issue type","Rule used","Reason (stored in the row)"],[[s["issue_type"].replace("_"," "),s["rule_id"],e(s["reason"])] for s in sorted(signals,key=lambda s:-s["current_count"])],["22%","20%","58%"],"tight")}
<div class="box ok"><b>Example hypothesis the dashboard shows</b> (noise and vibration, rule {next(s for s in signals if s['issue_type']=='noise_and_vibration')['rule_id']}):<br>{e(next(s for s in signals if s['issue_type']=='noise_and_vibration')['hypothesis'])}</div>
<h3>Hypothesis rules ({len(rules)})</h3>
{tbl(["Rule","Issue type","Applies when","Spec.","Source chunks cited"],[[r["rule_id"],r["issue_type"].replace("_"," ") if r["issue_type"]!="*" else "any",cond(r),r["specificity"],e(", ".join(r["source_chunk_ids"]) or "-")] for r in sorted(rules,key=lambda r:(r["issue_type"],-r["specificity"]))],["17%","20%","22%","6%","35%"],"tight")}
<p class="small">The highest specificity wins among the rules whose conditions hold. Texts are hypotheses ("not a confirmed cause") with concrete checks; the quality team can edit them in the table without a deploy. Placeholders: {{issue}}, {{batch}}, {{top_batch_events}}, {{current_count}}, {{prior_count}}, {{batch_share}}, {{batch_unit_share}}, {{batch_multiple}}, {{persists_share}}.</p>
<h3>Views the dashboard reads (bigquery/views/, to write)</h3>
{tbl(["View","Definition"],[
 ["<code>v_complaints_counted</code>","complaints where counts_as_complaint and consent_share; drops consumer_id, serial_number and raw_complaint; adds created_date; exposes redacted_complaint as the text"],
 ["<code>v_evidence_anonymised</code>","evidence joined to complaints where both consent flags are true; link, kind, duration"],
 ["<code>v_weekly_counts</code>","issue_type, week start (Monday), events, safety events, from the counted view"],
 ["<code>v_batch_events</code>","per issue type and batch in the current window: events, event share, units shipped to date, unit share, multiple"]],["26%","74%"],"tight")}
<p class="small">Dashboard API credentials should be able to read these views and <code>signals</code> and the factory tables, and write only <code>investigations</code>.</p>
""")

# ============================== PAGE 15: Phase 2 factory ==============================
tests, reps, rets, lots, chg = fac["end_of_line_tests"], fac["service_repairs"], fac["returns"], fac["batch_lots"], fac["change_records"]
def eol(b):
    t = [x for x in tests if x["batch_id"] == b]; n = len(t)
    return dict(db=S.mean(x["acoustic_db"] for x in t), over=sum(x["acoustic_db"] > 62 for x in t) / n, tq=sum(x["lock_torque_nm"] < .9 for x in t) / n, burn=sum(not x["burn_in_pass"] for x in t) / n, hot=sum(x["surface_temp_c_5min"] > 38 for x in t) / n)
ctrl = ["B-2026-03-A", "B-2026-04-A", "B-2026-06-D", "B-2026-08-A"]; cm = {k: S.mean(eol(b)[k] for b in ctrl) for k in ("db", "over", "tq", "burn", "hot")}
def story(b, chg_ids, key, label, fmt):
    r = eol(b); dx = C.Counter(x["diagnosis"] for x in reps if x["batch_id"] == b).most_common(2)
    return [b, "; ".join(f"{c['change_id']} {c['description']}" for c in chg if c["change_id"] in chg_ids), f"{label}: <b>{fmt(r[key])}</b> vs {fmt(cm[key])} for control batches", ", ".join(f"{d.replace('_',' ')} ({n})" for d, n in dx) + f"; {sum(x['batch_id']==b for x in rets)} returns"]
page("7.4 Phase 2: factory evidence", f"""
<h2 class="nb">7.4 Phase 2: factory evidence and investigation</h2>
<p>Your deck's last step checks the hypothesis against batch and quality-control factory data. Six tables hold that data (all fictional, generated by <code>data/generate_factory_data.py</code>, verified by <code>validate_factory_data.py</code>). Spec limits (<code>data/factory/spec_limits.json</code>): sound ≤ 62 dB at 30 cm, vibration ≤ 2.0 mm/s, lock torque 0.9 to 1.3 N·m, surface temperature ≤ 38 °C after 5 minutes, battery runtime ≥ 45 min. Sound and temperature follow <code>04_operating_specs.md</code>; torque and vibration limits are invented.</p>
{tbl(["Table","Rows","Key columns"],[
 ["<code>production_batches</code>",len(fac["production_batches"]),"batch_id, plant, lines, production dates, units_produced"],
 ["<code>batch_lots</code>",len(lots),"batch_id, component, lot_id, supplier, received_date, tooling_revision, change_note"],
 ["<code>change_records</code>",len(chg),"change_id, date, batch_id, type (supplier, tooling, test limit), description, approved_by"],
 ["<code>end_of_line_tests</code>",len(tests),"60 units per batch: line, shift, acoustic_db and limit used, vibration, lock_torque_nm, surface_temp_c_5min, runtime, burn_in_pass, gate_result"],
 ["<code>service_repairs</code>",len(reps),"repair_date, batch_id, diagnosis, part_replaced, warranty_covered, days_since_purchase, complaint_id (nullable)"],
 ["<code>product_returns</code>",len(rets),"return_date, batch_id, reason_code, resolution, complaint_id (nullable)"]],["24%","8%","68%"],"tight")}
<h3>The designed causes (so the investigation has something real to find)</h3>
{tbl(["Batch","Recorded change","End-of-line signature","Repairs and returns"],[
 story("B-2026-07-A",["CHG-0412","CHG-0425"],"db","Mean sound (dB)",lambda v:f"{v:.1f}")[:3]+[story("B-2026-07-A",["CHG-0412"],"db","",lambda v:"")[3]],
 story("B-2026-06-C",["CHG-0418"],"tq","Torque below 0.9 N·m (shifts B and C only)",lambda v:f"{v:.0%}"),
 story("B-2026-05-B",["CHG-0391"],"burn","Burn-in failures",lambda v:f"{v:.0%}")],["13%","33%","28%","26%"],"tight")}
<div class="box warn"><b>Controls and a red herring.</b> Batches 03-A, 04-A, 06-D and 08-A look normal. Batch 06-C also changed blade supplier (CHG-0420), but its blade tests are normal and shaving-performance complaints are flat, so a sound investigation should <i>not</i> blame the blades. In 07-A the acoustic gate was loosened to 64 dB on line L2 (CHG-0425), so noisy units passed.</div>
<h3>Investigation page and LLM assistant</h3>
{ul(["<b>Page</b>: for the selected signal, show the top batch against the other batches on the five end-of-line measures, supplier lots with change notes, change records, repairs by diagnosis, returns, and the suggested checks as a tickable list. <b>Open investigation</b> creates a row in <code>investigations</code>. A first sketch is the \"follow a signal\" view in <code>docs/database-viewer.html</code>.",
 "<b>LLM assistant (Phase 2)</b>: receives only computed facts (the signal row and these summaries), never raw private data, and returns wording and proposed actions. The numbers and the status always come from SQL; the assistant explains, it does not detect.",
 "Open point: whether to show the page in the prototype or keep it as a roadmap slide (decision for the team)."])}
""")

# ============================== PAGE 16: testing ==============================
def expected_chunks(c):
    ids = {k["chunk_id"] for k in kb if set(k["symptoms"]) & set(c["symptoms"]) and c["severity"] in k["severity_applicability"]}
    if c["severity"] == "high": ids |= {k["chunk_id"] for k in kb if k["document_type"] == "safety_escalation"}
    return ids
cc = [c for c in comp if c["counts_as_complaint"]]; exp_n = [len(expected_chunks(c)) for c in cc]
zero = sum(1 for n in exp_n if n == 0)
page("8. Testing", f"""
<h2 class="nb">8. Testing and evaluation</h2>
<p>Because severity, safety and signals are rules, they can be tested exactly. Because Gemini output varies, it is tested against labelled data with targets. The evaluation harness lives in <code>backend/tests/</code> and reads the JSON files in <code>data/</code>, so it never depends on cloud state. Targets marked <i>proposed</i> are for the team to confirm in milestone 1.</p>
{tbl(["Test","Data","Checks","Pass criterion"],[
 ["Derive rules (unit)","taxonomy_v2.json",f"All {len(tax['symptoms'])} symptoms; combinations: persists + low, loose head + persists, ask_question; safety flag equals severity high","100%, exact"],
 ["Stop-use rules (unit)","List of stop-use and near-miss phrases","Burnt, smoke, spark, shock, melt, detached head, liquid in port stop; \"warm\" does not, and triggers a follow-up instead","100% on the list"],
 ["Redaction (unit)","Phone and email samples","Removed from <code>redacted_complaint</code>","100%"],
 ["Extraction, text",f"{n_comp} complaint texts in x500_complaints_v2.json (labels are the answer)","Symptoms, issue type, severity, safety flag after derivation","<i>Proposed:</i> safety recall 100%; issue type ≥ 90%; symptom F1 ≥ 0.85"],
 ["Extraction, media","6 files + answer_key.json","must_have, may_have and must_not_have symptoms; derived fields; audio 2 must give the stop-use response","All must_have present, no must_not_have; derived fields equal"],
 ["Retrieval","Expected chunks per complaint (shared symptom, severity match; plus safety chunks when high)","Recall of expected chunks in the top 5; safety chunks always present for high severity; the 6 test files' <code>expected_chunks_retrieved</code>","<i>Proposed:</i> recall@5 ≥ 0.8; safety chunks 100%"],
 ["Grounding","Generated guidance for a sample","Every claim cites a retrieved chunk; uncited answers rejected","100% of rejected cases caught"],
 ["Signals oracle","bigquery/seed/signals_preview.ndjson","BigQuery <code>signals</code> equals the Python preview","Counts exact; rates within 0.1; same status and priority"],
 ["Data checks","validate_dataset.py, validate_factory_data.py","Windows, labels, batch concentration, designed contrasts, valid links","Script prints OK"],
 ["API flows","httpx against FastAPI","Happy path; safety path; a user cannot read another's reports; dashboard cannot read private columns","All pass"],
 ["Demo rehearsal","Section 1, \"What a successful demo shows\"","The five-point demo in section 1, end to end on the deployed system","Done twice without intervention"]],["15%","22%","40%","23%"],"tight")}
<p class="small">Coverage of the retrieval test as built: {len(cc)} complaints; the expected set has {min(exp_n)} to {max(exp_n)} chunks per complaint (median {int(S.median(exp_n))}); {'every complaint has at least one expected chunk' if zero == 0 else str(zero) + ' complaints have none, which is a gap in the knowledge base'}.</p>
<h3>Acceptance gate per milestone</h3>
{tbl(["Milestone","Gate"],[
 ["M0 Setup","Gemini \"hello\" from a laptop; Cloud Run \"hello\" URL; API contract agreed"],
 ["M1 Extraction","Text and media evaluations run and meet the targets, or the gaps are logged with a plan"],
 ["M2 Data","16 tables created and loaded; views exist; signals query matches the oracle; knowledge-base search passes the retrieval test"],
 ["M3 Chat backend","Full chat flow through the API, including the safety path and own-reports scoping"],
 ["M4 and M5 Apps","Consumer app and dashboard run against the deployed API with the demo data"],
 ["M6 Release","Everything deployed on Google Cloud; demo rehearsed; costs reviewed"]],["20%","80%"],"tight")}
""")

# ============================== PAGE 17: Google Cloud setup ==============================
env_lines = [l for l in open(ROOT / ".env.template").read().splitlines() if l and not l.startswith("#")]
page("9. Cloud setup and deploy", f"""
<h2 class="nb">9. Google Cloud setup, deployment and cost</h2>
<h3>9.1 First session (one person, about an hour)</h3>
{tbl(["Step","What to do"],[
 ["1. Project","Create a Google Cloud project, start the free trial, add budget alerts (for example $50 and $150). Choose one region for BigQuery, Cloud Storage, Firestore and Cloud Run, and check that the Gemini model you want is available there."],
 ["2. Tools","<code>brew install --cask google-cloud-sdk</code>; then <code>gcloud init</code>, <code>gcloud auth login</code>, <code>gcloud auth application-default login</code>, <code>gcloud config set project PROJECT_ID</code>. Optional: <code>firebase-tools</code> and <code>gh</code>."],
 ["3. APIs","<code>PROJECT_ID=... ./scripts/setup_gcp.sh</code> enables Vertex AI, BigQuery, Cloud Storage, Firestore, Cloud Run, Cloud Build, Artifact Registry and Secret Manager."],
 ["4. Python","Create a virtual environment, install <code>backend/</code> (pinned), copy <code>.env.template</code> to <code>.env</code> and fill it in."],
 ["5. Hello tests","A Gemini reply from a script; <code>gcloud run deploy productloop-api --source backend --region REGION</code> and open <code>/health</code>."],
 ["6. Dataset and bucket","Create the BigQuery dataset and the private media bucket; create the Firestore database (native mode)."]],["16%","84%"],"tight")}
<h3>9.2 Identity and permissions</h3>
<p>Locally the code runs as you (Application Default Credentials). Deployed, it runs as a <b>service account</b>. The classic failure is \"works on my laptop, 403 in the cloud\": the cloud service account is missing a role. Suggested roles (confirm names in the console; separate accounts for the consumer API and the dashboard API are recommended, not yet decided):</p>
{tbl(["Account","Roles","Why"],[
 ["Consumer API","Vertex AI User; BigQuery Job User + Data Editor on the dataset; Storage Object Admin on the media bucket; Cloud Datastore User (Firestore); Secret Manager Secret Accessor","Gemini and embeddings; write complaints, evidence; upload and read media; sessions; secrets"],
 ["Dashboard API","BigQuery Job User + Data Viewer (views, signals, factory tables) and Data Editor on <code>investigations</code> only; Storage Object Viewer","Read-only apart from investigations; cannot see private columns"],
 ["Both","Service Account Token Creator on itself, if signed URLs are generated from Cloud Run without a key file","Signed upload and read links"]],["16%","50%","34%"],"tight")}
<h3>9.3 Configuration (<code>.env.template</code>)</h3>
<pre>{e(chr(10).join(env_lines))}
# also pick, from the Vertex AI model list: GEMINI_MODEL_EXTRACT, GEMINI_MODEL_CHAT, EMBEDDING_MODEL</pre>
<h3>9.4 Deploy</h3>
{ul(["<b>Backend</b>: <code>gcloud run deploy productloop-api --source backend --region REGION</code>; later connect the GitHub repository to Cloud Build so each push to <code>main</code> redeploys. Set environment variables and secrets on the service; minimum instances 0.","<b>Apps</b>: <code>npm run build</code> in each app, then <code>firebase deploy --only hosting</code>. Call the API with its Cloud Run URL (configure CORS).","<b>Scheduled query</b>: create it in BigQuery from <code>bigquery/scheduled/signals.sql</code>, every 15 minutes, writing the <code>signals</code> table."])}
<h3>9.5 Cost expectations (figures from memory; verify on Google's pricing pages)</h3>
{tbl(["Item","Expectation"],[
 ["BigQuery","About zero at this size: the knowledge-base search scans under 1 MB; the 15-minute job stays inside the monthly free query allowance; storage is megabytes"],
 ["Gemini and embeddings","The main spend, especially audio and video tokens; hundreds of test runs should be single-digit dollars. Media is read once to keep this low"],
 ["Cloud Run, Firestore, Cloud Storage, Firebase Hosting","Scale to zero or inside free quotas at prototype volume"],
 ["Avoid","Deploying a Vertex AI Vector Search index (billed while deployed). Remember the free-trial credit expires after a set period"]],["30%","70%"],"tight")}
""")

# ============================== PAGE 18: work plan ==============================
page("10. Work plan", """
<h2 class="nb">10. Work plan and team split</h2>
<p>Planned for a one-week sprint (the hackathon window). Days overlap on purpose: the two front ends and the data work start as soon as the API contract and the seed data exist.</p>
"""+tbl(["Milestone","Days","Deliverables","Gate (see section 8)"],[
 ["<b>M0 Setup</b>","1","Google project, billing alert, <code>gcloud</code> login, APIs enabled, repository on GitHub, Gemini \"hello\", Cloud Run \"hello\", API contract agreed, models and region chosen","Hello tests pass"],
 ["<b>M1 Extraction</b>","1 to 3","<code>extract_from_media</code> and text extraction with the taxonomy schema; Pydantic models generated from <code>taxonomy_v2.json</code>; <code>derive.py</code>; <code>safety_rules.py</code>; evaluation harness for text and the six media files","Targets met or gaps logged"],
 ["<b>M2 Data</b>","2 to 4","Tables created and loaded from <code>bigquery/seed/</code>; embeddings for 41 chunks; <code>search_kb</code> and the retrieval test; four views; <code>signals.sql</code> scheduled and checked against the oracle","Signals equal the oracle; retrieval test passes"],
 ["<b>M3 Chat backend</b>","3 to 5","ADK agent, tools, callbacks, session service, chat endpoints, confirm and outcome flows, own-reports scoping, grounding check","API flow tests pass"],
 ["<b>M4 Consumer app</b>","4 to 6","Home, chat page with upload on attach, quick replies, confirm card, guidance with sources, safety screen, my reports","Runs against the deployed API"],
 ["<b>M5 Dashboard</b>","4 to 6","Tiles, signal list and detail, trend and batch charts, safety banner, evidence table, open investigation; investigation page if time allows","Shows the three emerging signals from BigQuery"],
 ["<b>M6 Release</b>","6 to 7","Cloud Build trigger, Firebase deploy, demo script and rehearsal, cost review, recorded real media if possible","Demo done twice"]],["14%","7%","57%","22%"],"tight")+"""
<h3>Suggested team split</h3>
"""+tbl(["Role","Owns","Starts with"],[
 ["AI and backend","backend/app: agent, tools, guardrails, rules, services, API","M0 hello tests, then M1 extraction and derive rules"],
 ["Data and BigQuery","bigquery/, data/, loader, views, signals query, retrieval test","Table creation and seed load as soon as the project exists; the oracle comparison"],
 ["Consumer front end","frontend/consumer","Static screens from the mockups against a mocked API, then the real API"],
 ["Dashboard front end","frontend/dashboard","Screens from the mockup against the signals preview JSON, then the real API"],
 ["Everyone","Reviews, tests, deployment, demo","Keep <code>data/taxonomy_v2.json</code> as the only place categories change"]],["20%","44%","36%"],"tight")+"""
<h3>Dependencies that unblock the others</h3>
"""+ul(["<b>API contract</b> (M0): lets both front ends build against mocks while the backend is written.","<b>Taxonomy models and <code>derive.py</code></b> (M1): used by the agent, the loader, tests and UI labels.","<b>Seed data in BigQuery</b> (M2): the dashboard needs it for real integration; before that it can read <code>bigquery/seed/signals_preview.ndjson</code>.","<b>Gemini access and a model name</b> (M0): nothing in Part 1 can be tested without them.","<b>Agreement on sessions and authentication</b> (open decisions, next page): needed before M3 ends."])+"""
<div class="box"><b>Definition of done for any task:</b> code in a pull request; unit tests for rules and tools; the relevant evaluation still meets its target; no secrets or personal data committed; the data and docs it touches are regenerated or updated.</div>
""")

# ============================== PAGE 19: risks, open decisions, limitations ==============================
page("11. Risks and open points", """
<h2 class="nb">11. Risks, open decisions and known limitations</h2>
<h3>11.1 Risks</h3>
"""+tbl(["Risk","Impact","Mitigation"],[
 ["Gemini misreads real audio or video","Wrong symptoms in the record","Test early on the six files and real recordings; the confirm card lets the user correct; low confidence triggers a question"],
 ["Chat feels slow (several model calls per turn)","Poor demo","Media read once; limit follow-ups to 3 or 4; use a fast model for the chat; keep retrieval to one query"],
 ["ADK learning curve or version changes","Delay","Pin the version; keep tools as plain functions; test callbacks in isolation"],
 ["<code>VECTOR_SEARCH</code> syntax or filtering behaves differently from the pattern","Retrieval delay","Spike in M2; fall back to tag filtering only, which already gives sourced answers"],
 ["Count change and rate change confuse viewers","Misread signals","Show both numbers and say which one drives the status"],
 ["SQL and the Python oracle disagree","Wrong signals on the dashboard","Oracle test in the pipeline; investigate any difference before the demo"],
 ["Permission errors only in the cloud (403)","Late surprises","Hello deploy in M0; service accounts per section 9; checklist"],
 ["Stop-use phrases missed in free text or audio","Safety gap","Rules plus the derived safety flag from extracted symptoms; err on the safe side; test list"],
 ["Cost from media tokens","Budget","Budget alerts; short clips; read media once; log call counts"],
 ["Synthetic data looks too tidy","Weak credibility","Say so plainly; record real media; keep messy and Hinglish cases in the tests"]],["30%","18%","52%"],"tight")+"""
<h3>11.2 Open decisions (owner to be named)</h3>
"""+ol(["<b>Authentication in the prototype</b>: a fixed demo user, a user picker, or Firebase Authentication (anonymous). Needed before M3 ends.",
 "<b>Session store when deployed</b>: a small custom Firestore session service for ADK, or ADK's database or Vertex-managed sessions (cost unverified). Development uses in-memory.",
 "<b>Model names and region</b> for Gemini and embeddings, and the embedding vector length.",
 "<b>TypeScript</b> for both React apps (recommended) or plain JavaScript.",
 "<b>Phase 2 investigation page</b> in the prototype, or on the roadmap only.",
 "<b>Evaluation targets</b> in section 8 marked proposed.",
 "<b>One service account or two</b> (consumer API and dashboard API); two are recommended."])+"""
<h3>11.3 Known limitations of what exists today</h3>
"""+ul(["All product, complaint, batch and factory data is <b>fictional</b>. Limits such as the lock-torque range are invented.",
 "The six test media files are stand-ins: audio is synthesised or text-to-speech; images and clips are edited from one third-party product photo with the brand removed. Keep them internal. Real recordings are a more honest test (<code>data/test_media/recording_script.md</code>).",
 "Nothing has been loaded into Google Cloud yet and no cloud code has run. The signals SQL, the four views, the loader and the deployment files are <b>not written</b>; the table definitions, seed files and the Python oracle are.",
 "ADK class and callback names were verified by installing the library, not by running an agent. The BigQuery vector query is a pattern to confirm. Cost figures are from memory.",
 "The dashboard and consumer mockups pre-date Data v2: use the numbers in section 5.2 and the chat flow in section 6.2.",
 "The hypothesis rules are hand-written from the product documents; they are hypotheses, not diagnoses."])+"""
""")

# ============================== PAGE 20: Appendix A ==============================
sev_tag = lambda v: f'<span class="tag {"t-hi" if v=="high" else "t-md" if v=="medium" else "t-lo"}">{v}</span>'
rows_a = []
for it, d in tax["issue_types"].items():
    for sy in d["symptoms"]:
        x = tax["symptoms"][sy]
        rows_a.append([f"<code>{it}</code>" if sy == d["symptoms"][0] else "", f"<code>{sy}</code>", sev_tag(x["default_severity"]), "stop" if x["safety"] else "", "" if x["counts_as_complaint"] else "question", e(x["description"])])
page("Appendix A: symptoms", f"""
<h2 class="nb">Appendix A: the {len(tax['symptoms'])} symptoms</h2>
{tbl(["Issue type","Symptom","Default severity","Stop-use","Counts","Meaning"],rows_a,["26%","27%","9%","7%","8%","23%"],"sym tight")}
<p class="small">From data/taxonomy_v2.json (version {e(tax['version'])}). Stop-use symptoms always derive severity high and safety flag true. "Question" symptoms (cleaning, storage, blade replacement, water exposure) mark user intent <code>ask_question</code> and are excluded from complaint counts. Symptoms are one global list: any symptom can be combined with any other.</p>
""")

# ============================== PAGE 21: Appendix B ==============================
def short(t): return re.sub(r"STRUCT<([^>]*)>", lambda m: "STRUCT<" + ", ".join(x.split()[0] for x in m.group(1).split(",")) + ">", t)
order = [k for k in NOTE_ROWS]
rows_b = []
for k in order:
    cols = schemas.get(k) or [tuple(c.split(" ", 1)) for c in SIG_COLS]
    rows_b.append([f"<code>{k}</code><br><span class='small'>{rowcount[k]} rows</span>", " · ".join(f"<b>{e(n)}</b> {e(short(t))}" for n, t in cols)])
page("Appendix B: table schemas", f"""
<h2 class="nb">Appendix B: table columns</h2>
{tbl(["Table","Columns (name and type)"],rows_b,["19%","81%"],"tight sch")}
<p class="small">Source: bigquery/tables.sql (16 tables) plus the columns of <code>signals</code>, which the scheduled query creates. Types are BigQuery types. NOT NULL markers are in the file. Browse the tables with real rows in docs/database-viewer.html.</p>
""")

# ============================== PAGE 22: Appendix C ==============================
page("Appendix C: glossary and files", """
<h2 class="nb">Appendix C: glossary and key files</h2>
"""+tbl(["Term","Meaning"],[
 ["ADK","Agent Development Kit, Google's open-source Python framework for agents: tools, callbacks, sessions, a Runner"],
 ["RAG","Retrieval-augmented generation: find relevant passages first, then let the model answer from them"],
 ["Chunk","One passage of the product documents stored as a row in <code>kb_chunks</code>"],
 ["Embedding","A list of numbers that represents the meaning of a text; similar meanings are close together"],
 ["VECTOR_SEARCH","BigQuery function that returns the rows whose embedding is closest to a query embedding"],
 ["Cosine distance","The measure used to compare embeddings; smaller means more similar"],
 ["Taxonomy","The fixed list of issue types and symptoms; the only place categories are defined"],
 ["Stop-use","A condition (burning smell, heat, sparks, detached head, liquid inside) where the user must stop using the product"],
 ["Grounding, cite-or-reject","Guidance must come from retrieved passages and cite them; an answer without valid citations is discarded"],
 ["Signal","A row in <code>signals</code>: an issue type whose complaints rise against the prior period, with status, priority and hypothesis"],
 ["Prior and current window","The 30 days before and the 30 days ending on the as-of date"],
 ["Rate per 1,000 units","Events divided by units shipped to date times 1,000; removes the effect of a growing installed base"],
 ["Batch multiple","A batch's share of events divided by its share of units shipped; 1x means no concentration"],
 ["Hypothesis rule","A row in <code>hypothesis_rules</code> that produces the hypothesis text and suggested checks for a signal"],
 ["Anonymised view","A BigQuery view that exposes only non-private columns of consented rows"],
 ["Signed URL","A temporary link that allows one upload or download without making the file public"],
 ["Service account","The identity deployed code runs as; permissions are granted to it with roles"]],["24%","76%"],"tight")+"""
<h3>Key files</h3>
"""+tbl(["File","Purpose"],[
 ["docs/ProductLoop_Dev_Guide.pdf","This guide (rebuild: <code>python3 docs/dev_guide_render.py</code>; content in <code>docs/build_dev_guide.py</code>)"],
 ["docs/database-viewer.html","Browse all 17 tables, schemas and rows; follow each signal across the factory data"],
 ["docs/consumer-app-prototype.html","Clickable consumer prototype: home, chat, confirm, guidance, safety override"],
 ["docs/quality-dashboard.html","Dashboard mockup (numbers pre-date Data v2)"],
 ["docs/ProductLoop_Architecture.pptx, ProductLoop_Tech_Stack.pdf, ProductLoop.pptx","Architecture slides, the earlier tech-stack summary, the pitch deck"],
 ["data/taxonomy_v2.md and .json","The vocabulary and the derivation rules"],
 ["data/kb_conflicts_log.md","The eight conflicts between source documents and how they were resolved"],
 ["data/test_media/answer_key.json, recording_script.md","Expected results for the six test files; how to record real ones"],
 ["bigquery/tables.sql, seed_src/, build_seed.py, preview_signals.py","Table definitions, thresholds and rules, seed builder, the signals oracle"]],["38%","62%"],"tight")+"""
""")
