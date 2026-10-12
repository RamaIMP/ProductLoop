"""Evaluation of the six media test files against data/test_media/answer_key.json. Needs a gcloud login. Run from backend/:
    PRODUCTLOOP_SKIP_DOTENV=1 ../productLoop_env/bin/python -m tests.eval.run_media_eval
Each file is sent with its typed message; the answer key lists must_have / may_have / must_not_have symptoms and the derived fields."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.rules.derive import derive
from app.tools.extract import extract_from_media

MEDIA = Path(__file__).resolve().parents[3] / "data" / "test_media"
REPORTS = Path(__file__).resolve().parent / "reports"


def run_case(case):
    msg = case["message_to_send"]
    msg = "" if msg.startswith("(no typed message") else msg
    t0 = time.time()
    try:
        e = extract_from_media([str(MEDIA / case["file"])], msg)
    except Exception as ex:  # keep the run going; report the failure
        return {"file": case["file"], "error": str(ex)[:300]}
    d = derive(e.symptoms, e.context, e.user_intent.value)
    got = {s.value for s in e.symptoms}
    exp = case["expected"]
    must, may, mnot = set(exp["must_have_symptoms"]), set(exp["may_have_symptoms"]), set(exp["must_not_have_symptoms"])
    derived_ok = (d.issue_type.value, d.severity.value, d.safety_flag) == (exp["derived"]["issue_type"], exp["derived"]["severity"], exp["derived"]["safety_flag"])
    return {
        "file": case["file"], "seconds": round(time.time() - t0, 1), "symptoms": sorted(got), "confidence": e.confidence,
        "context": {"persists": e.context.persists_after_cleaning.value, "charging": e.context.during_charging, "onset": e.context.onset.value},
        "derived": [d.issue_type.value, d.severity.value, d.safety_flag],
        "missing_must_have": sorted(must - got), "forbidden_present": sorted(got & mnot), "unexpected_extra": sorted(got - must - may - mnot),
        "derived_matches_key": derived_ok,
        "pass": not (must - got) and not (got & mnot) and derived_ok,
    }


def main():
    key = json.loads((MEDIA / "answer_key.json").read_text())
    with ThreadPoolExecutor(3) as ex:
        results = list(ex.map(run_case, key["cases"]))
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "media_eval.json").write_text(json.dumps(results, indent=1))
    for r in results:
        if "error" in r:
            print(f"ERROR {r['file']}: {r['error']}")
            continue
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['file']}  ({r['seconds']}s)  symptoms={r['symptoms']}  derived={r['derived']}")
        for k in ("missing_must_have", "forbidden_present", "unexpected_extra"):
            if r[k]:
                print(f"      {k}: {r[k]}")
        if not r["derived_matches_key"]:
            print(f"      derived differs from the answer key")
    print(f"\n{sum(r.get('pass', False) for r in results)}/{len(results)} files pass")


if __name__ == "__main__":
    main()
