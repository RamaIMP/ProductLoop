"""Evaluation harness for text extraction. Needs a gcloud login. Run from backend/:
    PRODUCTLOOP_SKIP_DOTENV=1 ../productLoop_env/bin/python -m tests.eval.run_text_eval [--limit N] [--model NAME]
Compares two designs on the labelled complaints in data/x500_complaints_v2.json:
  A  Gemini extracts symptoms and context; CODE derives issue type, severity, safety flag   (the design in the guide)
  B  Gemini is given the whole taxonomy JSON and decides everything itself                  (the alternative)"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from google.genai import types
from pydantic import BaseModel, Field

from app import config
from app.models.taxonomy import TAXONOMY, Derived, Extraction, IssueType, Severity
from app.rules.derive import derive
from app.services import gemini

DATA = Path(__file__).resolve().parents[3] / "data"
REPORTS = Path(__file__).resolve().parent / "reports"


class FullAnswer(Extraction):
    issue_type: IssueType
    severity: Severity
    safety_flag: bool


def _retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # rate limits and transient errors
            if i == tries - 1:
                return e
            time.sleep(2 * (i + 1))


def design_a(c, model):
    e = _retry(lambda: gemini.extract(c["raw_complaint"], model=model))
    if isinstance(e, Exception):
        return {"error": str(e)[:200]}
    d = derive(e.symptoms, e.context, e.user_intent.value)
    return {"symptoms": [s.value for s in e.symptoms], "issue_type": d.issue_type.value, "severity": d.severity.value, "safety_flag": d.safety_flag,
            "persists": e.context.persists_after_cleaning.value, "onset": e.context.onset.value, "confidence": e.confidence}


def design_b(c, model):
    system = ("You classify a consumer's report about an X500 shaver. The full taxonomy, including the derivation rules for issue_type, severity and safety_flag, "
              "is this JSON. Follow it exactly and output JSON matching the schema.\n" + json.dumps(TAXONOMY))
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.0, response_mime_type="application/json", response_schema=FullAnswer)

    def call():
        r = gemini.client().models.generate_content(model=model, contents=c["raw_complaint"], config=cfg)
        return FullAnswer.model_validate_json(r.text)

    a = _retry(call)
    if isinstance(a, Exception):
        return {"error": str(a)[:200]}
    own = derive(a.symptoms, a.context, a.user_intent.value)
    return {"symptoms": [s.value for s in a.symptoms], "issue_type": a.issue_type.value, "severity": a.severity.value, "safety_flag": a.safety_flag,
            "self_consistent": (own.issue_type.value, own.severity.value, own.safety_flag) == (a.issue_type.value, a.severity.value, a.safety_flag)}


def score(pairs, design):
    ok = [(c, r) for c, r in pairs if "error" not in r]
    n = len(ok)
    tp = fp = fn = 0
    for c, r in ok:
        g, p = set(c["symptoms"]), set(r["symptoms"])
        tp += len(g & p); fp += len(p - g); fn += len(g - p)
    pre, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    flagged = [(c, r) for c, r in ok if c["safety_flag"]]
    out = {
        "answered": n, "errors": len(pairs) - n,
        "issue_type_accuracy": sum(r["issue_type"] == c["issue_type"] for c, r in ok) / n,
        "severity_accuracy": sum(r["severity"] == c["severity"] for c, r in ok) / n,
        "safety_flag_accuracy": sum(r["safety_flag"] == c["safety_flag"] for c, r in ok) / n,
        "safety_recall": (sum(r["safety_flag"] for c, r in flagged) / len(flagged)) if flagged else None,
        "safety_missed": [c["complaint_id"] for c, r in flagged if not r["safety_flag"]],
        "safety_false_alarms": sum(r["safety_flag"] and not c["safety_flag"] for c, r in ok),
        "symptom_precision": pre, "symptom_recall": rec, "symptom_f1": 2 * pre * rec / max(pre + rec, 1e-9),
    }
    if design == "B":
        out["self_inconsistent_answers"] = sum(not r["self_consistent"] for c, r in ok)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=config.MODEL_EXTRACT)
    args = ap.parse_args()
    comps = json.loads((DATA / "x500_complaints_v2.json").read_text())["complaints"]
    if args.limit:
        comps = comps[: args.limit]
    t0 = time.time()
    done = [0]

    def timed(fn, c):
        s = time.time()
        r = fn(c, args.model)
        r["seconds"] = round(time.time() - s, 1)
        done[0] += 1
        if done[0] % 20 == 0:
            print(f"  {done[0]}/{2 * len(comps)} calls, {time.time() - t0:.0f}s elapsed", flush=True)
        return r

    with ThreadPoolExecutor(6) as ex:
        a = list(ex.map(lambda c: timed(design_a, c), comps))
        b = list(ex.map(lambda c: timed(design_b, c), comps))
    lat = sorted(r["seconds"] for r in a + b)
    print(f"latency per call: median {lat[len(lat)//2]}s, slowest {lat[-1]}s")
    res = {"model": args.model, "complaints": len(comps), "seconds": round(time.time() - t0),
           "A_code_decides": score(list(zip(comps, a)), "A"),
           "B_model_decides": score(list(zip(comps, b)), "B")}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "text_eval.json").write_text(json.dumps({"summary": res, "details": [{"id": c["complaint_id"], "text": c["raw_complaint"], "label": {k: c[k] for k in ("symptoms", "issue_type", "severity", "safety_flag")}, "A": ra, "B": rb} for c, ra, rb in zip(comps, a, b)]}, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
