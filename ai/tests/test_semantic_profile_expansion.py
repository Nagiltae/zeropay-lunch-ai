import json

from app import semantic_profile_expansion as expansion


def test_existing_profile_citation_must_match_current_source():
    old = {
        "items": [
            {
                "evidenceId": "E001",
                "sourceField": "sections.menu.items[0]",
                "content": {"name": "김치찌개"},
                "section": "menu",
                "status": "SUCCESS",
                "evidenceType": "menu",
            }
        ]
    }
    current = json.loads(json.dumps(old))
    assert expansion.evidence_compatible(["E001"], old, current)
    current["items"][0]["content"]["name"] = "된장찌개"
    assert not expansion.evidence_compatible(["E001"], old, current)


def test_batch_resume_does_not_repeat_successful_qwen_call(tmp_path, monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, timeout):
            assert timeout == 120.0

        def complete(self, system, prompt, schema):
            calls.append((system, prompt, schema))
            return json.dumps(
                {
                    "profileStatus": "READY",
                    "claims": [
                        {
                            "claimType": "FOOD_TYPE",
                            "text": "김치찌개 메뉴가 확인된다.",
                            "confidence": "HIGH",
                            "evidenceIds": ["E001"],
                        }
                    ],
                }
            )

        def close(self):
            pass

    monkeypatch.setattr(expansion, "OllamaClient", FakeClient)
    monkeypatch.setattr(expansion, "RUN_DIR", tmp_path / "profiles")
    monkeypatch.setattr(expansion, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(expansion, "PLAN_PATH", tmp_path / "plan.json")
    plan = {
        "inputSizeGatePass": True,
        "restaurants": [{"restaurantId": 42, "strictProfileReady": True}],
        "actions": {"REUSE_EXISTING": [], "GENERATE_NEW": [42]},
    }
    profile_input = {
        "restaurantId": 42,
        "venueId": None,
        "inputVersion": "test-v1",
        "inputHash": "input-hash",
        "quality": {"strictProfileReady": True, "lifecyclePresent": True},
    }
    evidence = {
        "evidenceId": "E001",
        "sourceField": "sections.menu.items[0]",
        "content": {"name": "김치찌개"},
        "section": "menu",
        "status": "SUCCESS",
        "evidenceType": "menu",
    }
    catalog = {"catalogVersion": "cat-v1", "catalogHash": "catalog-hash", "items": [evidence]}

    first = expansion.run_generation(plan, {42: (profile_input, catalog)})
    second = expansion.run_generation(plan, {42: (profile_input, catalog)})

    assert first["outcomes"]["42"]["status"] == "SUCCESS"
    assert second["outcomes"]["42"]["status"] == "SUCCESS"
    assert len(calls) == 1
