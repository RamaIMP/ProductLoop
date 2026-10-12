"""Builds load-ready NDJSON for every BigQuery table from ../data and seed_src/. Deterministic. Run: python3 build_seed.py"""
import json, hashlib, random, re, datetime as D
from pathlib import Path
HERE = Path(__file__).parent; DATA = HERE.parent / "data"; OUT = HERE / "seed"; OUT.mkdir(exist_ok=True)
rng = random.Random(7)
tax = json.load(open(DATA / "taxonomy_v2.json"))
comp = json.load(open(DATA / "x500_complaints_v2.json"))["complaints"]
batches = json.load(open(DATA / "batches.json"))["batches"]
kb = json.load(open(DATA / "x500_rag_knowledge_base_v2.json"))["chunks"]
TV = tax["version"]

def write(name, rows):
    with open(OUT / f"{name}.ndjson", "w") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{name:18} {len(rows):4} rows")

def redact(t):
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", t)
    return re.sub(r"(?<!\w)\+?\d[\d\s-]{8,}\d", "[phone]", t)

# taxonomy reference
write("taxonomy_symptoms", [dict(symptom=s, issue_type=d["issue_type"], default_severity=d["default_severity"], safety=d["safety"],
      counts_as_complaint=d["counts_as_complaint"], description=d["description"], taxonomy_version=TV) for s, d in tax["symptoms"].items()])

# batches and weekly shipments (equal split across the weeks since shipping began, up to the week of 2026-10-05)
write("batches", batches)
last_week = D.date(2026, 10, 5)
monday = lambda d: d - D.timedelta(days=d.weekday())
ship = []
for b in batches:
    start = monday(D.date.fromisoformat(b["ship_start"]))
    weeks = [start + D.timedelta(days=7 * i) for i in range((last_week - start).days // 7 + 1)]
    for region, total in (("India", b["units_shipped_india"]), ("United Kingdom", b["units_shipped_uk"])):
        base, rem = divmod(total, len(weeks))
        for i, w in enumerate(weeks): ship.append(dict(batch_id=b["batch_id"], region=region, week_start=w.isoformat(), units=base + (1 if i < rem else 0)))
write("shipments_weekly", ship)
bstart = {b["batch_id"]: D.date.fromisoformat(b["ship_start"]) for b in batches}

# complaints, registered units, evidence (units come from data/registered_units.json, made by generate_factory_data.py)
reg = {r["complaint_id"]: r for r in json.load(open(DATA / "registered_units.json"))}
DEMO = {"audio": ["audio1_rattling_grinding.m4a"], "voice": ["audio2_spoken_burnt_smell.m4a"],
        "video": ["video1_loose_head_wobble.mp4", "video2_charging_led_off.mp4"], "photo": ["image1_hair_buildup_under_head.jpg", "image2_worn_blade_surface.jpg"]}
rows, evid = [], []
for n, c in enumerate(comp, 1):
    cid = c["complaint_id"]; u = reg[cid]; cons, serial = u["consumer_id"], u["serial_number"]
    consent = not (not c["counts_as_complaint"] and n % 3 == 0)      # a few questions are not shared, to exercise the filter
    rows.append(dict(complaint_id=cid, created_at=c["timestamp"], updated_at=c["timestamp"], consumer_id=cons, serial_number=serial,
        batch_reference=c["batch_reference"], region=c["region"], product_model=c["product_model"], user_intent=c["user_intent"],
        incident_country=None, incident_region=None, incident_city=None, location_source=None,
        input_types=c["input_type"], language=c["language"], complaint_summary='Reported findings: ' + ', '.join(s.replace('_', ' ') for s in c['symptoms']) + '.',
        symptoms=c["symptoms"], context=c["context"], issue_type=c["issue_type"], severity=c["severity"], safety_flag=c["safety_flag"],
        confidence=c["confidence"], counts_as_complaint=c["counts_as_complaint"], guidance_outcome=c["guidance_outcome"],
        status={"helped": "resolved", "not_helped": "unresolved"}.get(c["guidance_outcome"], "awaiting_feedback"),
        submitted_at=c["timestamp"], resolved_at=None, ticket_id=None, callback=None,
        consent_share=consent, taxonomy_version=TV))
    for k, uri in enumerate(c["media_uri"]):
        ext = uri.rsplit(".", 1)[1]; kind = "photo" if ext == "jpg" else "video" if ext == "mp4" else ("voice" if "voice" in c["input_type"] else "audio")
        evid.append(dict(evidence_id=f"{cid}-{k+1}", complaint_id=cid, kind=kind, gcs_uri=uri, demo_file=rng.choice(DEMO[kind]),
            duration_seconds=None if kind == "photo" else 8, consent_share=consent, created_at=c["timestamp"],
            extraction_status="not_recorded", extracted_symptoms=[], extracted_context=None, extracted_summary=None,
            extraction_confidence=None, extraction_model=None, extraction_model_version=None,
            extraction_prompt_version=None, extracted_at=None))
units = [{k: v for k, v in r.items() if k != "complaint_id"} for r in reg.values()]
write("complaints", rows); write("registered_units", units); write("evidence", evid)
# Historical seeds contain no event log or per-file model output. Do not fabricate either.
write("complaint_events", [])

# knowledge base (embeddings are added by load_data.py)
write("kb_chunks", [dict(chunk_id=k["chunk_id"], product_model=k["product_model"], source_file=k["source_file"], section=k["section"],
      document_type=k["document_type"], issue_types=k["issue_types"], symptoms=k["symptoms"], severity_applicability=k["severity_applicability"],
      safety_critical=k["safety_critical"], title=k["title"], content=k["content"], embedding=None, embedding_model=None, taxonomy_version=TV) for k in kb])

# config and rules
write("signal_config", [json.load(open(HERE / "seed_src" / "signal_config.json"))])
write("hypothesis_rules", json.load(open(HERE / "seed_src" / "hypothesis_rules.json")))
