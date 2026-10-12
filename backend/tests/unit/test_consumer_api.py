from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_intake_uses_dummy_extractor_and_derives_category():
    response = client.post("/api/intake", json={"user_id": "demo-user", "message": "My shaver is rattling and shaking."})
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "confirm_report"
    assert body["derived"]["issue_type"] == "noise_and_vibration"


def test_intake_stops_unsafe_text_before_extraction():
    response = client.post("/api/intake", json={"user_id": "demo-user", "message": "It smells burnt when charging."})
    assert response.status_code == 200
    assert response.json()["action"] == "stop_use"


def test_intake_recognises_hair_trapped_under_the_shaving_head():
    response = client.post("/api/intake", json={"user_id": "demo-user", "message": "There is hair stuck in the blade."})
    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["symptoms"] == ["hair_buildup"]
    assert body["derived"]["issue_type"] == "cleaning_and_maintenance"


def test_greeting_gets_a_conversational_response_without_starting_a_complaint():
    response = client.post("/api/intake", json={"user_id": "demo-user", "message": "hi"})
    assert response.status_code == 200
    assert response.json() == {
        "action": "greeting",
        "message": "Hi! I can help with that. Please describe what is happening, or attach a photo, sound recording, or video.",
    }


def test_media_upload_uses_development_fallback_and_combines_prior_symptoms():
    response = client.post(
        "/api/media/extract",
        data={"prior_symptoms_json": '["increased_noise"]'},
        files={"file": ("hair_buildup_under_head.jpg", b"not-a-real-image", "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_mode"] == "development_fallback"
    assert body["extraction"]["symptoms"] == ["increased_noise", "hair_buildup"]


def test_each_non_safety_issue_type_gets_a_relevant_follow_up():
    cases = {
        "noise_and_vibration": "My shaver rattles.",
        "shaving_performance": "It pulls my hair.",
        "power_and_charging": "The battery drains fast.",
        "shaving_head_and_fitment": "The head wobbles.",
        "cleaning_and_maintenance": "Hair is stuck in the blade.",
    }
    for expected_type, message in cases.items():
        response = client.post("/api/intake", json={"user_id": "demo-user", "message": message})
        body = response.json()
        assert body["derived"]["issue_type"] == expected_type
        assert body["follow_up"]["question"]


def test_follow_up_uses_text_reasoning_result(monkeypatch):
    monkeypatch.setattr("app.api.consumer.gemini.write_follow_up", lambda **_: "Have you already tried cleaning the blade units?")
    response = client.post("/api/conversation/follow-up", json={
        "extraction": {"product_model": "X500", "user_intent": "report_problem", "symptoms": ["pulling_hair"], "context": {}, "confidence": 0.9},
        "derived": {"issue_type": "shaving_performance", "severity": "medium", "safety_flag": False},
        "follow_up": {"field": "persists_after_cleaning", "question": "Have you cleaned the blade units?", "replies": ["Yes", "No"]},
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Have you already tried cleaning the blade units?", "replies": ["Yes", "No"], "mode": "text_reasoning_llm"}


def test_confirm_then_save_outcome_and_list_own_reports():
    payload = {
        "user_id": "consumer-a",
        "consent_share": True,
        "extraction": {
            "product_model": "X500",
            "user_intent": "report_problem",
            "symptoms": ["rattling_sound"],
            "context": {"onset": "this_week", "persists_after_cleaning": "not_tried", "during_charging": False},
            "confidence": 0.9,
        },
    }
    created = client.post("/api/reports/confirm", json=payload)
    assert created.status_code == 201
    report_id = created.json()["report"]["report_id"]
    updated = client.post(f"/api/reports/{report_id}/outcome", json={"outcome": "helped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
    reports = client.get("/api/reports", params={"user_id": "consumer-a"})
    assert len(reports.json()) == 1


def test_unresolved_report_raises_a_ticket():
    created = client.post("/api/reports/confirm", json={
        "user_id": "consumer-b",
        "extraction": {
            "product_model": "X500", "user_intent": "report_problem", "symptoms": ["battery_drains_fast"],
            "context": {"onset": "longer", "persists_after_cleaning": "not_applicable", "during_charging": False}, "confidence": 0.9,
        },
    })
    report_id = created.json()["report"]["report_id"]
    updated = client.post(f"/api/reports/{report_id}/outcome", json={"outcome": "not_fixed"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "ticket_raised"
    assert updated.json()["ticket_id"].startswith("SR-")


def test_callback_can_only_be_requested_for_a_raised_ticket():
    created = client.post("/api/reports/confirm", json={
        "user_id": "consumer-c",
        "extraction": {"product_model": "X500", "user_intent": "report_problem", "symptoms": ["battery_drains_fast"], "context": {}, "confidence": 0.9},
    })
    report_id = created.json()["report"]["report_id"]
    assert client.post(f"/api/reports/{report_id}/callback", json={"slot": "Today · 2:00–2:30 PM"}).status_code == 409
    client.post(f"/api/reports/{report_id}/outcome", json={"outcome": "not_fixed"})
    callback = client.post(f"/api/reports/{report_id}/callback", json={"slot": "Today · 2:00–2:30 PM"})
    assert callback.status_code == 200
    assert callback.json()["callback"]["slot"] == "Today · 2:00–2:30 PM"
