"""Creates fictional factory, service and returns data for the quality side. Deterministic. Run from data/: python3 generate_factory_data.py"""
import json, csv, random, datetime as D
from pathlib import Path
rng = random.Random(2026)
OUT = Path("factory"); OUT.mkdir(exist_ok=True)
batches = {b["batch_id"]: b for b in json.load(open("batches.json"))["batches"]}
complaints = json.load(open("x500_complaints_v2.json"))["complaints"]
d = D.date.fromisoformat
def dump(name, rows):
    json.dump(rows, open(OUT / f"{name}.json", "w"), indent=1, ensure_ascii=False)
    with open(OUT / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(rows[0].keys())
        for r in rows: w.writerow([("|".join(v) if isinstance(v, list) else v) for v in r.values()])
    print(f"{name:20} {len(rows):4} rows")

# ---------- production
PROD = {"B-2026-03-A": ("2026-03-03", "2026-03-20"), "B-2026-04-A": ("2026-04-06", "2026-04-24"), "B-2026-05-B": ("2026-05-04", "2026-05-22"),
        "B-2026-06-C": ("2026-06-01", "2026-06-19"), "B-2026-06-D": ("2026-06-22", "2026-07-03"), "B-2026-07-A": ("2026-07-06", "2026-07-24"),
        "B-2026-08-A": ("2026-08-03", "2026-08-21")}
dump("production_batches", [dict(batch_id=b, plant="Plant A (fictional)", lines=["L1", "L2"], production_start=s, production_end=e,
     units_produced=int(batches[b]["units_shipped_total"] * 1.06)) for b, (s, e) in PROD.items()])

# ---------- component lots (one lot per component per batch) with the designed changes
COMP = ["motor_assembly", "motor_bearing", "lock_ring", "head_assembly", "blade_unit", "battery_pack", "charging_circuit", "casing"]
BASE = dict(motor_assembly="M-1", motor_bearing="BR-1", lock_ring="LR-1", head_assembly="H-1", blade_unit="BL-1", battery_pack="BAT-1", charging_circuit="CC-1", casing="C-1")
CHANGES = {("B-2026-07-A", "motor_bearing"): ("BR-2", None, "First lot from new bearing supplier BR-2"),
           ("B-2026-06-C", "lock_ring"): ("LR-1", "T2", "Lock ring moulded on new tool T2"),
           ("B-2026-05-B", "charging_circuit"): ("CC-3", None, "First lot from new charging-circuit supplier CC-3"),
           ("B-2026-06-C", "blade_unit"): ("BL-2", None, "New blade supplier BL-2")}
lots = []
for b, (ps, pe) in PROD.items():
    for c in COMP:
        sup, tool, note = CHANGES.get((b, c), (BASE[c], "T1" if c == "lock_ring" else None, None))
        recv = d(ps) - D.timedelta(days=rng.randint(10, 28))
        lots.append(dict(batch_id=b, component=c, lot_id=f"{c[:3].upper()}-{sup}-{recv:%m%d}", supplier=sup, received_date=recv.isoformat(),
                         quantity=int(batches[b]["units_shipped_total"] * 1.06), tooling_revision=tool, change_note=note))
dump("batch_lots", lots)
dump("change_records", [
 dict(change_id="CHG-0412", date="2026-06-24", batch_id="B-2026-07-A", type="supplier_change", description="Motor bearing supplier changed from BR-1 to BR-2", approved_by="Procurement"),
 dict(change_id="CHG-0418", date="2026-05-28", batch_id="B-2026-06-C", type="tooling_change", description="Lock ring mould tool replaced: T1 to T2", approved_by="Manufacturing engineering"),
 dict(change_id="CHG-0391", date="2026-04-27", batch_id="B-2026-05-B", type="supplier_change", description="Charging-circuit supplier changed from CC-1 to CC-3", approved_by="Procurement"),
 dict(change_id="CHG-0420", date="2026-05-30", batch_id="B-2026-06-C", type="supplier_change", description="Blade supplier changed from BL-1 to BL-2", approved_by="Procurement"),
 dict(change_id="CHG-0425", date="2026-07-07", batch_id="B-2026-07-A", type="test_limit_change", description="End-of-line acoustic limit raised from 62 dB to 64 dB on line L2 to reduce rejects", approved_by="Line quality lead")])

# ---------- end-of-line tests: 60 sampled units per batch. Fictional spec limits.
def clip(v, lo, hi): return max(lo, min(hi, v))
tests = []
for b, (ps, pe) in PROD.items():
    days = (d(pe) - d(ps)).days
    for i in range(60):
        day = d(ps) + D.timedelta(days=rng.randint(0, days)); shift = rng.choice("ABC"); line = rng.choice(["L1", "L2"])
        ac, vib, tq, temp, run, burn = rng.gauss(58.3, 1.4), rng.gauss(1.2, .25), rng.gauss(1.10, .07), rng.gauss(34.0, 1.5), rng.gauss(47, 1.5), rng.random() > .006
        limit = 62.0
        if b == "B-2026-07-A":
            ac, vib = rng.gauss(61.2, 2.2), rng.gauss(1.65, .4)
            if line == "L2": limit = 64.0                       # the loosened gate (CHG-0425)
        if b == "B-2026-06-C" and shift in "BC": tq = rng.gauss(0.82, .08)
        if b == "B-2026-05-B": temp, burn = rng.gauss(37.4, 2.6), rng.random() > .10
        tests.append(dict(unit_test_id=f"EOL-{b[2:]}-{i+1:03d}", batch_id=b, test_date=day.isoformat(), line=line, shift=shift,
            acoustic_db=round(ac, 1), acoustic_limit_used_db=limit, vibration_rms_mm_s=round(clip(vib, .3, 4), 2), lock_torque_nm=round(clip(tq, .4, 1.6), 2),
            surface_temp_c_5min=round(clip(temp, 28, 52), 1), battery_runtime_min=round(run, 1), burn_in_pass=burn,
            gate_result="pass" if (ac <= limit and burn) else "fail"))
dump("end_of_line_tests", tests)
SPEC = dict(acoustic_db_max=62.0, vibration_rms_mm_s_max=2.0, lock_torque_nm=[0.9, 1.3], surface_temp_c_5min_max=38.0, battery_runtime_min_min=45.0, note="Fictional limits. Sound and temperature ranges follow Data_synthetic/04_operating_specs.md; torque and vibration limits are invented.")
json.dump(SPEC, open(OUT / "spec_limits.json", "w"), indent=1)

# ---------- registered units: one per complaint, so serial number gives the batch
import hashlib
rng_u = random.Random(7)
consumers = [f"u_{i:04d}" for i in range(1, 86)]
reg_list, reg, cs = [], {}, {}
for n, c in enumerate(complaints, 1):
    bs = d(batches[c["batch_reference"]]["ship_start"]); day = d(c["timestamp"][:10])
    purchase = max(min(day - D.timedelta(days=2), bs + D.timedelta(days=rng_u.randint(7, 45))), bs)
    serial = f"X5-{c['batch_reference'][2:].replace('-', '')}-{n:05d}"
    row = dict(serial_number=serial, batch_id=c["batch_reference"], region=c["region"], purchase_date=purchase.isoformat(),
               consumer_id=consumers[int(hashlib.sha1(c["complaint_id"].encode()).hexdigest(), 16) % len(consumers)], complaint_id=c["complaint_id"])
    reg_list.append(row); reg[serial] = row; cs[c["complaint_id"]] = serial
json.dump(reg_list, open("registered_units.json", "w"), indent=1)
print(f"{'registered_units':20} {len(reg_list):4} rows (data/registered_units.json)")

# ---------- service repairs and returns, linked to complaints where a registered unit exists
CENTRES = ["Service Centre Mumbai", "Service Centre Delhi", "Service Centre Bengaluru", "Service Centre London"]
DX = {  # category -> weighted diagnoses (diagnosis, part replaced)
 "noise_and_vibration": [("motor_bearing_noise", "motor_assembly", 6), ("head_fit_loose", "lock_ring", 2), ("blade_unit_worn", "blade_unit", 1), ("no_fault_found", None, 1)],
 "shaving_head_and_fitment": [("lock_ring_cracked", "lock_ring", 4), ("lock_ring_stripped", "lock_ring", 2), ("head_joint_damaged", "head_assembly", 1), ("no_fault_found", None, 1)],
 "heat_and_safety": [("charging_circuit_fault", "charging_circuit", 5), ("battery_overheat", "battery_pack", 2), ("user_damage_liquid", None, 1)],
 "power_and_charging": [("battery_aged", "battery_pack", 3), ("port_damage_user", "casing", 2), ("no_fault_found", None, 2)],
 "shaving_performance": [("blade_unit_worn", "blade_unit", 6), ("no_fault_found", None, 2)],
 "cleaning_and_maintenance": [("no_fault_found", None, 3), ("blade_unit_worn", "blade_unit", 1)]}
def pick(cat):
    opts = DX[cat]; r = rng.random() * sum(o[2] for o in opts); a = 0
    for o in opts:
        a += o[2]
        if r <= a: return o[0], o[1]
    return opts[-1][0], opts[-1][1]
repairs, n = [], 0
def add_repair(day, batch, region, serial, cid, cat):
    global n; n += 1
    dx, part = pick(cat); pd = D.date.fromisoformat(reg[serial]["purchase_date"]) if serial in reg else None
    repairs.append(dict(repair_id=f"R{n:04d}", repair_date=day.isoformat(), batch_id=batch, region=region, serial_number=serial, complaint_id=cid,
        service_centre=rng.choice(CENTRES[3:] if region == "United Kingdom" else CENTRES[:3]), diagnosis=dx, part_replaced=part,
        warranty_covered=dx not in ("port_damage_user", "user_damage_liquid"), days_since_purchase=(day - pd).days if pd else rng.randint(20, 160)))
# from complaints: share of each rising category leads to a repair
LINK = {"noise_and_vibration": .45, "shaving_head_and_fitment": .55, "heat_and_safety": .8, "power_and_charging": .25, "shaving_performance": .12, "cleaning_and_maintenance": .0}
for c in complaints:
    if not c["counts_as_complaint"] or rng.random() > LINK.get(c["issue_type"], 0): continue
    add_repair(d(c["timestamp"][:10]) + D.timedelta(days=rng.randint(3, 14)), c["batch_reference"], c["region"], cs[c["complaint_id"]], c["complaint_id"], c["issue_type"])
# walk-in repairs without a logged complaint, batch-dependent
WALK = {"B-2026-07-A": ("noise_and_vibration", 8), "B-2026-06-C": ("shaving_head_and_fitment", 3), "B-2026-05-B": ("heat_and_safety", 2),
        "B-2026-03-A": ("shaving_performance", 4), "B-2026-04-A": ("power_and_charging", 4), "B-2026-06-D": ("shaving_performance", 3), "B-2026-08-A": ("cleaning_and_maintenance", 1)}
for b, (cat, k) in WALK.items():
    for _ in range(k):
        lo = max(d(batches[b]["ship_start"]) + D.timedelta(days=30), D.date(2026, 8, 8))
        day = lo + D.timedelta(days=rng.randint(0, (D.date(2026, 10, 6) - lo).days))
        add_repair(day, b, "India", f"X5-W{rng.randint(10000, 99999)}", None, cat)
repairs.sort(key=lambda r: r["repair_date"])
for i, r in enumerate(repairs, 1): r["repair_id"] = f"R{i:04d}"
dump("service_repairs", repairs)

RC = {"noise_and_vibration": "noise_vibration", "shaving_head_and_fitment": "head_loose", "heat_and_safety": "overheating", "power_and_charging": "charging_fault", "shaving_performance": "poor_shave", "cleaning_and_maintenance": "other", "other_or_unclear": "other"}
rets, m = [], 0
for c in complaints:
    p = {"noise_and_vibration": .3, "shaving_head_and_fitment": .3, "heat_and_safety": .5}.get(c["issue_type"], .05)
    if c["counts_as_complaint"] and rng.random() < p:
        m += 1; rets.append(dict(return_id=f"RT{m:04d}", return_date=(d(c["timestamp"][:10]) + D.timedelta(days=rng.randint(5, 21))).isoformat(), batch_id=c["batch_reference"],
            region=c["region"], serial_number=cs[c["complaint_id"]], complaint_id=c["complaint_id"], reason_code=RC[c["issue_type"]], resolution=rng.choice(["refund", "replacement"])))
for b, k in {"B-2026-07-A": 6, "B-2026-06-C": 2, "B-2026-05-B": 2, "B-2026-03-A": 2, "B-2026-04-A": 2, "B-2026-06-D": 1}.items():
    for _ in range(k):
        m += 1; day = D.date(2026, 8, 8) + D.timedelta(days=rng.randint(0, 58))
        rets.append(dict(return_id=f"RT{m:04d}", return_date=day.isoformat(), batch_id=b, region="India", serial_number=f"X5-W{rng.randint(10000, 99999)}", complaint_id=None,
            reason_code={"B-2026-07-A": "noise_vibration", "B-2026-06-C": "head_loose", "B-2026-05-B": "overheating"}.get(b, rng.choice(["poor_shave", "charging_fault", "other"])), resolution=rng.choice(["refund", "replacement"])))
rets.sort(key=lambda r: r["return_date"])
for i, r in enumerate(rets, 1): r["return_id"] = f"RT{i:04d}"
dump("returns", rets)
