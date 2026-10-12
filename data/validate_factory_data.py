"""Checks that the factory data shows the designed contrasts. Run from data/: python3 validate_factory_data.py"""
import json, statistics as S, collections as C
F = lambda n: json.load(open(f"factory/{n}.json"))
tests, rep, ret, lots = F("end_of_line_tests"), F("service_repairs"), F("returns"), F("batch_lots")
batches = {b["batch_id"]: b for b in json.load(open("batches.json"))["batches"]}
comp = [c for c in json.load(open("x500_complaints_v2.json"))["complaints"] if c["counts_as_complaint"]]
print(f"{'batch':13}{'dB mean':>8}{'>62dB':>7}{'gate fail':>10}{'torque<0.9':>11}{'burn fail':>10}{'temp>38':>8}{'repairs':>8}{'returns':>8}{'compl/1000u':>12}")
for b in batches:
    t = [x for x in tests if x["batch_id"] == b]; n = len(t)
    r = sum(x["batch_id"] == b for x in rep); rt = sum(x["batch_id"] == b for x in ret)
    cp = sum(c["batch_reference"] == b for c in comp) / batches[b]["units_shipped_total"] * 1000
    print(f"{b:13}{S.mean(x['acoustic_db'] for x in t):8.1f}{sum(x['acoustic_db']>62 for x in t)/n:7.0%}{sum(x['gate_result']=='fail' for x in t)/n:10.0%}"
          f"{sum(x['lock_torque_nm']<0.9 for x in t)/n:11.0%}{sum(not x['burn_in_pass'] for x in t)/n:10.0%}{sum(x['surface_temp_c_5min']>38 for x in t)/n:8.0%}{r:8}{rt:8}{cp:12.2f}")
print("\n06-C torque below 0.9 by shift:", {s: f"{sum(x['lock_torque_nm']<0.9 for x in tests if x['batch_id']=='B-2026-06-C' and x['shift']==s)}/{sum(1 for x in tests if x['batch_id']=='B-2026-06-C' and x['shift']==s)}" for s in "ABC"})
print("07-A acoustic limit used:", dict(C.Counter((x["line"], x["acoustic_limit_used_db"]) for x in tests if x["batch_id"] == "B-2026-07-A")))
print("\nTop repair diagnoses per batch:")
for b in batches:
    c = C.Counter(x["diagnosis"] for x in rep if x["batch_id"] == b); print(f"  {b}: {dict(c.most_common(3))}")
# assertions: the designed contrasts, and normal controls
mean = lambda b, k: S.mean(x[k] for x in tests if x["batch_id"] == b)
ctrl = [b for b in batches if b not in ("B-2026-07-A", "B-2026-06-C", "B-2026-05-B")]
assert mean("B-2026-07-A", "acoustic_db") - S.mean(mean(b, "acoustic_db") for b in ctrl) > 2.0
assert all(abs(mean(b, "acoustic_db") - 58.3) < 1.0 for b in ctrl)
assert sum(x["lock_torque_nm"] < .9 for x in tests if x["batch_id"] == "B-2026-06-C" and x["shift"] in "BC") / sum(1 for x in tests if x["batch_id"] == "B-2026-06-C" and x["shift"] in "BC") > .5
assert sum(not x["burn_in_pass"] for x in tests if x["batch_id"] == "B-2026-05-B") / 60 >= .07
assert all(sum(not x["burn_in_pass"] for x in tests if x["batch_id"] == b) / 60 < .04 for b in ctrl)
ids = {c["complaint_id"] for c in comp}
assert all(r["complaint_id"] in ids for r in rep if r["complaint_id"]) and all(r["complaint_id"] in ids for r in ret if r["complaint_id"])
print("\nOK: designed contrasts present, controls normal, links valid")
