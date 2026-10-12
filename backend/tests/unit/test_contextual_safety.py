from app.guardrails.safety_rules import safety_response
from app.models.taxonomy import Extraction
from app.rules.derive import derive
from app.api.consumer import intake, IntakeRequest


def test_persistent_fitment_keeps_safety_but_not_electrical_advice():
    extraction = Extraction(symptoms=['unclear_description', 'head_not_fitting'],
                            context={'persists_after_cleaning': 'yes'}, confidence=1)
    assert [s.value for s in extraction.symptoms] == ['head_not_fitting']
    assert derive(extraction.symptoms, extraction.context).safety_flag
    result = intake(IntakeRequest(user_id='safety-test', message='The head still does not fit', extraction=extraction))
    text = ' '.join(result['response']['steps'])
    assert 'securely attached' in text
    assert 'charg' not in text.lower()


def test_combined_hazards_preserve_both_precautions():
    text = ' '.join(safety_response(['head_not_fitting', 'sparking'])['steps'])
    assert 'securely attached' in text
    assert 'charging' in text
    assert 'safe to do so' in text


def test_unclear_alone_is_preserved():
    assert Extraction(symptoms=['unclear_description'], confidence=.3).symptoms[0].value == 'unclear_description'


def test_mechanical_and_unknown_hazards_still_stop_use():
    assert 'jammed' in ' '.join(safety_response(['grinding_with_resistance'])['steps'])
    assert 'damaged' in ' '.join(safety_response(['visible_damage'])['steps'])
    assert 'Stop using' in safety_response([])['steps'][0]
