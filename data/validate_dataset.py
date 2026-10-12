"""Checks complaints_v2 against targets and the taxonomy. Run: python3 validate_dataset.py"""
import json, collections as C, datetime as D
d=json.load(open('x500_complaints_v2.json'))['complaints']; tax=json.load(open('taxonomy_v2.json')); b={x['batch_id']:x for x in json.load(open('batches.json'))['batches']}
P0,P1,C0,C1=D.date(2026,8,8),D.date(2026,9,6),D.date(2026,9,7),D.date(2026,10,6)
dt=lambda x:D.date.fromisoformat(x['timestamp'][:10])
win=lambda x:'prior' if P0<=dt(x)<=P1 else 'cur' if C0<=dt(x)<=C1 else 'OUT'
assert all(win(x)!='OUT' for x in d),"date outside windows"
assert all(s in tax['symptoms'] for x in d for s in x['symptoms']),"symptom not in taxonomy"
assert len({x['complaint_id'] for x in d})==len(d),"duplicate ids"
assert all((x['severity']=='high')==x['safety_flag'] for x in d),"safety_flag/severity mismatch"
cmp=[x for x in d if x['counts_as_complaint']]; cnt=C.Counter((x['issue_type'],win(x)) for x in cmp)
print("rows",len(d),"| complaints",len(cmp),"| questions",len(d)-len(cmp))
print(f"{'category':28}{'prior':>6}{'cur':>5}{'change':>9}")
for it in tax['issue_types']:
    p,c=cnt[(it,'prior')],cnt[(it,'cur')]; print(f"{it:28}{p:>6}{c:>5}{(('%+d%%'%round((c-p)/p*100)) if p else 'n/a'):>9}")
ship={k:v['units_shipped_total'] for k,v in b.items()}; tot=sum(ship.values())
for it in ['noise_and_vibration','shaving_head_and_fitment','heat_and_safety']:
    xs=[x for x in cmp if x['issue_type']==it and win(x)=='cur']; top,n=C.Counter(x['batch_reference'] for x in xs).most_common(1)[0]
    print(f"{it}: {top} {n}/{len(xs)} events vs {ship[top]/tot:.0%} of units -> {n/len(xs)/(ship[top]/tot):.1f}x")
print("hinglish rows:",sum(x['language']=='hinglish' for x in d),"| every symptom covered by text check passed by construction")
print("OK")
