"""Builds docs/database-viewer.html: a read-only browser for every table (schema + rows) plus a 'follow a signal' page."""
import json, re, statistics as S, collections as C
from pathlib import Path
H = Path(__file__).parent; ROOT = H.parent; SEED = H / "seed"; FAC = ROOT / "data" / "factory"
nd = lambda n: [json.loads(l) for l in open(SEED / f"{n}.ndjson")]
js = lambda p: json.load(open(p))

# ---- schemas parsed from tables.sql
sql = re.sub(r"--[^\n]*", "", open(H / "tables.sql").read())
def split_top(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "<(": depth += 1
        if ch in ">)": depth -= 1
        if ch == "," and depth == 0: out.append(cur.strip()); cur = ""
        else: cur += ch
    return out + ([cur.strip()] if cur.strip() else [])
schemas = {}
for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \(", sql):
    i, depth = m.end(), 1; j = i
    while depth:
        depth += {"(": 1, ")": -1}.get(sql[j], 0); j += 1
    cols = []
    for part in split_top(sql[i:j - 1]):
        mm = re.match(r"(\w+)\s+(.+?)(\s+NOT NULL)?$", " ".join(part.split()))
        cols.append(dict(name=mm.group(1), type=mm.group(2), required=bool(mm.group(3))))
    schemas[m.group(1)] = cols
schemas["signals"] = [dict(name=n, type=t, required=False) for n, t in [
 ("computed_at", "TIMESTAMP"), ("issue_type", "STRING"), ("window_start", "DATE"), ("window_end", "DATE"), ("current_count", "INT64"), ("prior_count", "INT64"),
 ("change_pct", "FLOAT64"), ("rate_current_per_1000", "FLOAT64"), ("rate_prior_per_1000", "FLOAT64"), ("rate_change_pct", "FLOAT64"), ("safety_count", "INT64"),
 ("persists_share", "FLOAT64"), ("top_batch", "STRING"), ("top_batch_events", "INT64"), ("batch_event_share", "FLOAT64"), ("batch_unit_share", "FLOAT64"),
 ("batch_multiple", "FLOAT64"), ("top_symptoms", "ARRAY<STRUCT<symptom STRING, n INT64>>"), ("evidence_count", "INT64"), ("status", "STRING"),
 ("priority", "STRING"), ("reason", "STRING"), ("rule_id", "STRING"), ("hypothesis", "STRING"), ("actions", "ARRAY<STRING>")]]

# ---- data per table
D_ = {}
for n in ["taxonomy_symptoms", "batches", "shipments_weekly", "registered_units", "complaints", "evidence", "complaint_events", "kb_chunks", "signal_config", "hypothesis_rules"]: D_[n] = nd(n)
D_["signals"] = nd("signals_preview")
for n in ["production_batches", "batch_lots", "change_records", "end_of_line_tests", "service_repairs"]: D_[n] = js(FAC / f"{n}.json")
D_["product_returns"] = js(FAC / "returns.json"); D_["investigations"] = []
for r in D_["kb_chunks"]: r["embedding"] = None
for r in D_["batches"]: r.pop("units_shipped_total", None) if False else None

GROUPS = [("Consumer side", ["complaints", "evidence", "complaint_events", "registered_units", "kb_chunks"]),
          ("Reference and settings", ["taxonomy_symptoms", "signal_config", "hypothesis_rules"]),
          ("Quality side: output", ["signals", "investigations"]),
          ("Quality side: batches and shipping", ["batches", "shipments_weekly", "production_batches"]),
          ("Quality side: factory evidence", ["batch_lots", "change_records", "end_of_line_tests", "service_repairs", "product_returns"])]
NOTES = {
 "complaints": "One incident per complaint_id, owned by consumer_id. Drafts must not count in analytics. These historical seeds are submitted: status is derived from guidance_outcome (helped → resolved; not_helped → unresolved; none → awaiting_feedback). Actual resolution times and ticket/callback details are unknown. region remains the country/market; separate incident-location fields are unknown. Private identity and raw text must be excluded from quality views.",
 "evidence": "Each file links to complaints via complaint_id. Files live in Cloud Storage; demo_file is a representative fixture, not necessarily evidence matching that complaint. Extraction fields are reserved for per-file model findings; historical seeds have not_recorded status and no invented extraction outputs.",
 "complaint_events": "Append-only incident history, joined by complaint_id; media events can also link evidence_id. Empty because the historical fixtures contain no actual event log. Event IDs must be deduplicated during ingestion.",
 "registered_units": "Serial number gives the batch, so the consumer never types it.", "kb_chunks": "41 passages from the product documents. The embedding column is filled when the loader runs (empty here).",
 "taxonomy_symptoms": "The controlled vocabulary: each symptom has an issue type, a default severity and a stop-use flag.", "signal_config": "Thresholds for 'Emerging' and priority, as data not code.",
 "hypothesis_rules": "Rule-based hypotheses with suggested checks; placeholders are filled by the signals job.",
 "signals": "PREVIEW. This is what the 15-minute job should write, computed here in Python from the same data. The BigQuery query will be checked against it.",
 "investigations": "Empty until someone clicks 'Open investigation'.", "batches": "Production batches and units shipped.",
 "shipments_weekly": "Units shipped per batch, region and week; used for rates per 1,000 units.", "production_batches": "Plant, lines and dates for each batch.",
 "batch_lots": "One supplier lot per component per batch. Notes mark the supplier or tooling changes.", "change_records": "Approved changes that affect batches.",
 "end_of_line_tests": "60 sampled units per batch: sound, vibration, lock torque, temperature, burn-in.", "service_repairs": "Repair diagnoses; some link back to a complaint.",
 "product_returns": "Returns by batch and reason; some link back to a complaint."}
tables = [dict(name=t, group=g, rows=D_[t], schema=schemas[t], note=NOTES[t]) for g, ts in GROUPS for t in ts]

# ---- 'follow a signal': for each emerging signal, the top batch vs the other batches across factory evidence
tests, reps, rets, lots, chg = D_["end_of_line_tests"], D_["service_repairs"], D_["product_returns"], D_["batch_lots"], D_["change_records"]
def eol(b):
    t = [x for x in tests if x["batch_id"] == b]; n = len(t)
    return dict(acoustic_mean=round(S.mean(x["acoustic_db"] for x in t), 1), over_62db=sum(x["acoustic_db"] > 62 for x in t) / n,
        torque_low=sum(x["lock_torque_nm"] < .9 for x in t) / n, burn_fail=sum(not x["burn_in_pass"] for x in t) / n, temp_over_38=sum(x["surface_temp_c_5min"] > 38 for x in t) / n)
others_for = lambda b: [x for x in {t["batch_id"] for t in tests} if x != b]
follow = []
for s in D_["signals"]:
    if s["status"] != "emerging": continue
    b = s["top_batch"]; mine = eol(b); oth = [eol(o) for o in others_for(b)]
    metrics = [dict(label=l, this=mine[k], others=S.mean(o[k] for o in oth), fmt=f) for k, l, f in
        [("acoustic_mean", "Sound at end of line (dB, mean)", "db"), ("over_62db", "Units over 62 dB", "pct"), ("torque_low", "Lock torque below 0.9 N·m", "pct"),
         ("burn_fail", "Burn-in failures", "pct"), ("temp_over_38", "Surface temp over 38 °C", "pct")]]
    dx = C.Counter(x["diagnosis"] for x in reps if x["batch_id"] == b)
    follow.append(dict(issue_type=s["issue_type"], batch=b, reason=s["reason"], hypothesis=s["hypothesis"], actions=s["actions"], metrics=metrics,
        diagnoses=dx.most_common(4), repairs=sum(x["batch_id"] == b for x in reps), returns=sum(x["batch_id"] == b for x in rets),
        changes=[dict(id=c["change_id"], text=c["description"], date=c["date"]) for c in chg if c["batch_id"] == b],
        lots=[dict(component=l["component"], lot=l["lot_id"], note=l["change_note"]) for l in lots if l["batch_id"] == b and l["change_note"]]))

payload = json.dumps(dict(tables=tables, follow=follow, dataset="productloop"), ensure_ascii=False).replace("</", "<\\/")
html = open(H / "viewer_template.html").read().replace("/*DATA*/", "const DB = " + payload + ";")
out = ROOT / "docs" / "database-viewer.html"; out.write_text(html, encoding="utf8")
print("wrote", out, f"({out.stat().st_size // 1024} KB)", "|", len(tables), "tables,", sum(len(t['rows']) for t in tables), "rows,", len(follow), "signals followed")
