import pytest

from app.guardrails.safety_rules import check_stop_use, mentions_warmth
from app.models.taxonomy import SYMPTOM_INFO


@pytest.mark.parametrize("text", [
    "it smells burnt when I charge it",
    "There is a burning smell from the charger",
    "I saw smoke coming from the shaver",
    "I saw a spark near the charging port",
    "it makes a crackling, popping sound",
    "I got a small electric shock",
    "it gets very hot after two minutes",
    "it is too hot to hold",
    "the shaver started to overheat",
    "the plastic near the head has melted",
    "the casing has a crack",
    "the lock ring looks cracked",
    "the head came off while it was running",
    "the shaving head fell off during use",
    "water got into the charging port",
    "I dropped it in the sink",
    "it grinds and struggles like the motor is stuck",
    "I can see an internal part through a gap",
    "Mera X500: jalne ki smell aa rahi hai.",
    "Mera X500: chingari dikhi.",
    "Mera X500: bahut zyada garam ho jaata hai.",
])
def test_stop_use_phrases_are_caught(text):
    assert check_stop_use(text), text


@pytest.mark.parametrize("text", [
    "it is much louder than before",
    "it vibrates a lot and rattles",
    "the battery dies after ten minutes",
    "it pulls my beard",
    "how do I clean the blades properly?",
    "can I use it in the shower?",
    "it gives me razor burn",
    "there is no burning smell, just a loud noise",
    "it does not get hot, it only rattles",
    "I use it after a hot shower and hot water",
    "the head wobbles while it runs",
])
def test_normal_complaints_do_not_trigger(text):
    assert check_stop_use(text) is None, text


@pytest.mark.parametrize('text', [
    'It won’t charge. There is no heat, smoke, or burning smell.',
    'It will not charge. No heat, smoke or burning smell.',
    'There is no smoke or burning smell.',
    'There is no smoke, heat and burning smell.',
    'Neither smoke nor burning smell is present.',
    'It stopped without smoke or sparks.',
    'No signs of heat, smoke, or burning smell. It will not charge.',
    'NO HEAT, SMOKE, OR BURNING SMELL.',
    'No heat,\n smoke,\n or burning smell.',
])
def test_negated_hazard_lists_do_not_override_extracted_meaning(text):
    assert check_stop_use(text) is None


@pytest.mark.parametrize(('text', 'symptom'), [
    ('No heat or burning smell, but it sparks.', 'sparking'),
    ('There is no smoke, but there is a burning smell.', 'burning_smell'),
    ('No heat, smoke, or burning smell. The head came off during use.', 'head_detached'),
    ('No heat or smoke; water got into the charging port.', 'water_ingress'),
    ('There was smoke yesterday, but no smoke or burning smell now.', 'burning_smell'),
    ('No smoke, burning smell started later.', 'burning_smell'),
    ('No heat or smoke, and the casing is cracked.', 'visible_damage'),
    ('The shaver sparked, without heat or smoke.', 'sparking'),
    ('No smoke. It grinds and the motor is jammed.', 'grinding_with_resistance'),
])
def test_negated_list_does_not_hide_separate_positive_hazards(text, symptom):
    result = check_stop_use(text)
    assert result is not None
    assert symptom in result.symptoms


def test_warm_alone_asks_a_question_instead_of_stopping():
    assert check_stop_use("it gets warm after a minute") is None
    assert mentions_warmth("it gets warm after a minute")
    assert not mentions_warmth("it gets very hot after a minute")


def test_returns_the_implied_symptoms():
    s = check_stop_use("it smells burnt while charging")
    assert "burning_smell" in s.symptoms


def test_catches_every_labelled_complaint_with_a_stop_use_symptom(complaints):
    missed = [(c["complaint_id"], c["raw_complaint"]) for c in complaints
              if any(SYMPTOM_INFO[s]["safety"] for s in c["symptoms"]) and not check_stop_use(c["raw_complaint"])]
    assert not missed, missed


def test_does_not_trigger_on_complaints_without_a_stop_use_symptom(complaints):
    false_alarms = [(c["complaint_id"], c["raw_complaint"]) for c in complaints
                    if not any(SYMPTOM_INFO[s]["safety"] for s in c["symptoms"]) and check_stop_use(c["raw_complaint"])]
    assert not false_alarms, false_alarms
