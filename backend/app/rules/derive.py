"""Derives issue type, severity and safety flag from the symptoms Gemini extracted. Plain rules, no model.
Rules are written in data/taxonomy_v2.md (section 'Derivation rules') and checked against the labelled complaints."""
from collections.abc import Iterable

from app.models.taxonomy import ISSUE_PRIORITY, SYMPTOM_INFO, Context, Derived

_RANK = {"low": 0, "medium": 1, "high": 2}
_NOT_RAISED_BY_PERSISTENCE = {"cleaning_and_maintenance", "other_or_unclear"}
_FIT_ISSUE = "shaving_head_and_fitment"
_FIT_SYMPTOMS = {"head_loose", "head_wobble", "head_not_fitting", "blade_unit_not_seated"}


def derive(symptoms: Iterable[str], context: Context | dict | None = None, user_intent: str = "report_problem") -> Derived:
    syms = [getattr(s, "value", s) for s in symptoms]
    if not syms:
        raise ValueError("at least one symptom is required")
    ctx = context if isinstance(context, Context) else Context(**(context or {}))
    persists = ctx.persists_after_cleaning.value

    top = max(_RANK[SYMPTOM_INFO[s]["default_severity"]] for s in syms)
    severity = [k for k, v in _RANK.items() if v == top][0]
    candidates = [SYMPTOM_INFO[s]["issue_type"] for s in syms if _RANK[SYMPTOM_INFO[s]["default_severity"]] == top]
    issue_type = min(candidates, key=ISSUE_PRIORITY.index)

    if severity == "low" and persists == "yes" and issue_type not in _NOT_RAISED_BY_PERSISTENCE:
        severity = "medium"
    if issue_type == _FIT_ISSUE and persists == "yes" and _FIT_SYMPTOMS & set(syms):
        severity = "high"  # a head that cannot be secured must not be used (03_safety_escalation.md)
    if user_intent == "ask_question" and not any(SYMPTOM_INFO[s]["safety"] for s in syms):
        severity = "low"
    return Derived(issue_type=issue_type, severity=severity, safety_flag=severity == "high")
