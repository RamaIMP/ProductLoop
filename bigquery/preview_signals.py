"""Computes what the 15-minute signals job should output, in Python, from the seed files.
Used as a preview and as the oracle the BigQuery SQL is checked against. Run: python3 preview_signals.py"""
import json, datetime as D
from pathlib import Path
H = Path(__file__).parent; S = H / "seed"
L = lambda n: [json.loads(l) for l in open(S / f"{n}.ndjson")]
cfg = L("signal_config")[0]; rules = L("hypothesis_rules"); tax = L("taxonomy_symptoms"); ship = L("shipments_weekly")
if cfg.get('batch_rate_alerts_enabled') is False:
    raise SystemExit('This legacy preview requires shipment-rate analysis. The current config is count-based; wire the count-based signal generator before generating signals.')
comp = [c for c in L("complaints") if c["counts_as_complaint"] and c["consent_share"]]; ev = L("evidence")
d = D.date.fromisoformat
as_of = d(cfg["as_of_date"]); W = cfg["window_days"]
cur_s, cur_e = as_of - D.timedelta(days=W - 1), as_of; pri_e = as_of - D.timedelta(days=W); pri_s = as_of - D.timedelta(days=2 * W - 1)
period = lambda c: "cur" if cur_s <= d(c["created_at"][:10]) <= cur_e else "prior" if pri_s <= d(c["created_at"][:10]) <= pri_e else None
units = lambda end: sum(s["units"] for s in ship if d(s["week_start"]) <= end)
batch_units = lambda b: sum(s["units"] for s in ship if s["batch_id"] == b and d(s["week_start"]) <= cur_e)
U_cur, U_pri, U_all = units(cur_e), units(pri_e), units(cur_e)
ev_by = {}
for e in ev: ev_by.setdefault(e["complaint_id"], []).append(e) if e["consent_share"] else None
pct = lambda x: f"{round(x * 100)}%"
out = []
for it in sorted({t["issue_type"] for t in tax}):
    cs = [c for c in comp if c["issue_type"] == it]; cur = [c for c in cs if period(c) == "cur"]; pri = [c for c in cs if period(c) == "prior"]
    n, p = len(cur), len(pri); safety = sum(c["safety_flag"] for c in cur)
    rc, rp = n / U_cur * 1000, p / U_pri * 1000; rchg = (rc / rp - 1) * 100 if rp > 0 else None
    known = [c for c in cur if c["context"]["persists_after_cleaning"] in ("yes", "no")]
    persists = sum(c["context"]["persists_after_cleaning"] == "yes" for c in known) / len(known) if known else None
    bc = {}
    for c in cur:
        if c["batch_reference"]: bc[c["batch_reference"]] = bc.get(c["batch_reference"], 0) + 1
    top, topn = (sorted(bc.items(), key=lambda kv: (-kv[1], kv[0]))[0] if bc else (None, 0))
    ushare = batch_units(top) / U_all if top else None; eshare = topn / n if n else None
    mult = eshare / ushare if (top and n >= cfg["min_batch_events"] and ushare) else None
    syms = {}
    for c in cur:
        for s in c["symptoms"]: syms[s] = syms.get(s, 0) + 1
    topsym = [dict(symptom=k, n=v) for k, v in sorted(syms.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    eff_min = cfg["min_events_safety"] if (n and safety / n >= cfg["safety_share_min"]) else cfg["min_events"]
    grows = lambda t: p == 0 or (rchg is not None and rchg >= t)
    if n >= eff_min and grows(cfg["growth_pct"]): status = "emerging"
    elif safety > 0 or (n >= cfg["watch_min_events"] and grows(cfg["watch_growth_pct"])): status = "watching"
    elif n < cfg["watch_min_events"]: status = "low_volume"
    else: status = "stable"
    priority = "high" if status == "emerging" and (safety > 0 or (mult or 0) >= cfg["batch_multiple_flag"]) else "medium" if status in ("emerging", "watching") else "low"
    cand = [r for r in rules if r["issue_type"] in (it, "*") and (r["min_batch_multiple"] is None or (mult or 0) >= r["min_batch_multiple"])
            and (r["min_persists_share"] is None or (persists or 0) >= r["min_persists_share"])]
    r = max(cand, key=lambda r: r["specificity"])
    fill = lambda t: (t.replace("{issue}", it.replace("_", " ").capitalize()).replace("{batch}", top or "").replace("{top_batch_events}", str(topn))
        .replace("{current_count}", str(n)).replace("{prior_count}", str(p)).replace("{batch_share}", pct(eshare) if eshare is not None else "")
        .replace("{batch_unit_share}", pct(ushare) if ushare is not None else "").replace("{batch_multiple}", f"{mult:.1f}" if mult else "")
        .replace("{persists_share}", pct(persists) if persists is not None else ""))
    reason = f"{n} events in the last {W} days vs {p} in the previous period" + (f"; batch {top} is {mult:.1f}x its share of units" if mult else "") + (f"; {safety} safety-flagged" if safety else "")
    out.append(dict(computed_at=f"{as_of}T12:00:00Z", issue_type=it, window_start=str(cur_s), window_end=str(cur_e), current_count=n, prior_count=p,
        change_pct=round((n - p) / p * 100, 1) if p else None, rate_current_per_1000=round(rc, 3), rate_prior_per_1000=round(rp, 3),
        rate_change_pct=round(rchg, 1) if rchg is not None else None, safety_count=safety, persists_share=round(persists, 3) if persists is not None else None,
        top_batch=top, top_batch_events=topn, batch_event_share=round(eshare, 3) if eshare is not None else None,
        batch_unit_share=round(ushare, 3) if ushare else None, batch_multiple=round(mult, 2) if mult else None, top_symptoms=topsym,
        evidence_count=sum(len(ev_by.get(c["complaint_id"], [])) for c in cur), status=status, priority=priority, reason=reason,
        rule_id=r["rule_id"], hypothesis=fill(r["hypothesis"]), actions=[fill(a) for a in r["actions"]]))
with open(S / "signals_preview.ndjson", "w") as f:
    for o in out: f.write(json.dumps(o, ensure_ascii=False) + "\n")
if __name__ == "__main__":
    print(f"window {cur_s} to {cur_e} vs {pri_s} to {pri_e}")
    print(f"{'issue_type':28}{'cur':>4}{'prior':>6}{'rate chg':>10}{'safety':>7}  {'top batch':13}{'mult':>6}  {'status':10}{'priority':9}rule")
    for o in out: print(f"{o['issue_type']:28}{o['current_count']:>4}{o['prior_count']:>6}{(str(o['rate_change_pct'])+'%') if o['rate_change_pct'] is not None else 'n/a':>10}{o['safety_count']:>7}  {str(o['top_batch']):13}{str(o['batch_multiple']):>6}  {o['status']:10}{o['priority']:9}{o['rule_id']}")
