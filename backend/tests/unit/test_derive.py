import json
from pathlib import Path

import pytest

from app.models.taxonomy import SYMPTOM_INFO, Context, Extraction
from app.rules.derive import derive


def test_taxonomy_copy_is_in_sync():
    root = Path(__file__).resolve().parents[3]
    assert (root / "data" / "taxonomy_v2.json").read_text() == (root / "backend" / "app" / "taxonomy_v2.json").read_text()


def test_matches_every_labelled_complaint(complaints):
    wrong = []
    for c in complaints:
        d = derive(c["symptoms"], c["context"], c["user_intent"])
        got = (d.issue_type.value, d.severity.value, d.safety_flag)
        if got != (c["issue_type"], c["severity"], c["safety_flag"]):
            wrong.append((c["complaint_id"], got, (c["issue_type"], c["severity"], c["safety_flag"])))
    assert not wrong, wrong


@pytest.mark.parametrize("symptom", sorted(SYMPTOM_INFO))
def test_single_symptom_uses_its_default(symptom):
    info = SYMPTOM_INFO[symptom]
    d = derive([symptom], {"persists_after_cleaning": "not_tried"})
    assert d.severity.value == info["default_severity"]
    assert d.issue_type.value == info["issue_type"]
    assert d.safety_flag == (info["default_severity"] == "high")


def test_stop_use_symptoms_are_always_high_and_flagged():
    for s, info in SYMPTOM_INFO.items():
        if info["safety"]:
            assert derive(["increased_noise", s], {}).safety_flag


def test_highest_severity_symptom_picks_the_issue_type():
    d = derive(["increased_noise", "increased_vibration", "excessive_heat"], {})
    assert (d.issue_type.value, d.severity.value) == ("heat_and_safety", "high")


def test_persisting_after_cleaning_raises_low_to_medium():
    assert derive(["increased_noise"], {"persists_after_cleaning": "yes"}).severity.value == "medium"
    assert derive(["increased_noise"], {"persists_after_cleaning": "no"}).severity.value == "low"
    assert derive(["hair_buildup"], {"persists_after_cleaning": "yes"}).severity.value == "low"  # cleaning topics are exempt
    assert derive(["unclear_description"], {"persists_after_cleaning": "yes"}).severity.value == "low"


def test_head_that_cannot_be_secured_is_high():
    assert derive(["head_loose"], {"persists_after_cleaning": "yes"}).safety_flag
    assert not derive(["head_loose"], {"persists_after_cleaning": "no"}).safety_flag
    assert not derive(["head_loose"], {"persists_after_cleaning": "not_tried"}).safety_flag


def test_questions_stay_low_unless_a_stop_use_symptom_is_present():
    assert derive(["cleaning_question"], {}, "ask_question").severity.value == "low"
    assert derive(["increased_vibration"], {}, "ask_question").severity.value == "low"
    assert derive(["burning_smell"], {}, "ask_question").safety_flag


def test_needs_a_symptom():
    with pytest.raises(ValueError):
        derive([], {})


def test_extraction_model_rejects_unknown_symptoms_and_dedupes():
    with pytest.raises(Exception):
        Extraction(symptoms=["not_a_symptom"], confidence=0.9)
    e = Extraction(symptoms=["increased_noise", "increased_noise"], confidence=0.9, context=Context())
    assert [s.value for s in e.symptoms] == ["increased_noise"]
