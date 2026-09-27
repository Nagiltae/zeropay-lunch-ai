import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.menu_budget_classifier import (
    ClassificationBatchError,
    GeminiMenuBudgetClassifier,
    RequestPacer,
    classify_with_bounded_retry,
    merge_chunk_result,
)


def test_merge_rejects_unknown_duplicate_ids_and_invalid_enums():
    menus = [{"id": 1, "name": "meal"}]
    with pytest.raises(ClassificationBatchError, match="unknown output"):
        merge_chunk_result(menus, [{"menuId": 2, "budgetEligibility": "UNKNOWN", "flags": []}])
    with pytest.raises(ClassificationBatchError, match="duplicate output"):
        merge_chunk_result(
            menus,
            [
                {"menuId": 1, "budgetEligibility": "UNKNOWN", "flags": []},
                {"menuId": 1, "budgetEligibility": "UNKNOWN", "flags": []},
            ],
        )
    with pytest.raises(ClassificationBatchError, match="invalid classification schema"):
        merge_chunk_result(menus, [{"menuId": 1, "budgetEligibility": "MAYBE", "flags": []}])


def test_omitted_menu_is_fail_safe_unknown_in_input_order():
    result = merge_chunk_result(
        [{"id": 8}, {"id": 9}],
        [{"menuId": 9, "budgetEligibility": "INELIGIBLE", "flags": ["DRINK"]}],
    )
    assert result == [
        {"menuId": 8, "budgetEligibility": "UNKNOWN", "flags": []},
        {"menuId": 9, "budgetEligibility": "INELIGIBLE", "flags": ["DRINK"]},
    ]


def test_gemini_sdk_structured_request_uses_only_existing_menu_fields():
    class Models:
        request = None

        def generate_content(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                text='{"classifications":[{"menuId":12,"budgetEligibility":"UNKNOWN","flags":[]}]}',
                usage_metadata=None,
            )

    models = Models()
    classifier = GeminiMenuBudgetClassifier(
        api_key="test-only-not-a-secret", client=SimpleNamespace(models=models)
    )
    result, usage = classifier.classify(
        [{"id": 12, "name": "item", "description": None, "priceValue": 1200}]
    )

    assert result == [{"menuId": 12, "budgetEligibility": "UNKNOWN", "flags": []}]
    assert usage == {}
    assert models.request["model"] == "gemini-3.8-flash"
    assert models.request["config"].response_mime_type == "application/json"
    assert "priceValue" in models.request["contents"]
    assert "user budget" not in models.request["contents"].lower()
    assert "restaurantId" not in models.request["contents"]


def test_transient_network_failure_is_retried_once_only():
    class HttpError(Exception):
        __module__ = "httpx"

    class FakeClassifier:
        calls = 0

        def classify(self, menus):
            self.calls += 1
            if self.calls == 1:
                raise HttpError("network")
            return [{"menuId": 1, "budgetEligibility": "ELIGIBLE", "flags": []}], {}

    client = FakeClassifier()
    outcome = classify_with_bounded_retry(client, [{"id": 1}], sleep=lambda _: None)
    assert client.calls == 2
    assert outcome["attempts"] == 2
    assert outcome["retries"] == 1


def test_transient_5xx_failure_is_retried_once_only():
    class ApiError(Exception):
        code = 503

    class FakeClassifier:
        calls = 0

        def classify(self, menus):
            self.calls += 1
            if self.calls == 1:
                raise ApiError("server")
            return [{"menuId": 1, "budgetEligibility": "UNKNOWN", "flags": []}], {}

    client = FakeClassifier()
    outcome = classify_with_bounded_retry(client, [{"id": 1}], sleep=lambda _: None)
    assert client.calls == 2
    assert outcome["attempts"] == 2
    assert outcome["retries"] == 1


def test_pacer_enforces_minimum_interval_without_sleeping_in_tests():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    pacer = RequestPacer(3.0, sleep=sleep, monotonic=lambda: now[0])
    assert pacer.before_request() == 0
    now[0] += 0.75
    assert pacer.before_request() == 2.25
    assert sleeps == [2.25]
    assert pacer.before_request() == 3.0


def test_resumed_pacer_accounts_for_elapsed_time_since_saved_request():
    now = [10.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    pacer = RequestPacer(
        3.0,
        sleep=sleep,
        monotonic=lambda: now[0],
        elapsed_since_last_request=2.0,
    )
    assert pacer.before_request() == 1.0
    assert sleeps == [1.0]


def test_retry_pacing_applies_to_initial_and_retry_requests():
    calls = []

    class ApiError(Exception):
        code = 503

    class FakeClassifier:
        count = 0

        def classify(self, menus):
            self.count += 1
            if self.count == 1:
                raise ApiError("safe test exception")
            return [{"menuId": 1, "budgetEligibility": "UNKNOWN", "flags": []}], {}

    outcome = classify_with_bounded_retry(
        FakeClassifier(),
        [{"id": 1}],
        sleep=lambda _: None,
        before_request=lambda: calls.append("paced"),
    )
    assert calls == ["paced", "paced"]
    assert outcome["attempts"] == 2


@pytest.mark.parametrize("status", [400, 403, 429])
def test_nontransient_client_failure_is_not_retried(status):
    class ApiError(Exception):
        code = status

    class FakeClassifier:
        calls = 0

        def classify(self, menus):
            self.calls += 1
            raise ApiError("safe test exception")

    client = FakeClassifier()
    with pytest.raises(ClassificationBatchError) as caught:
        classify_with_bounded_retry(client, [{"id": 1}], sleep=lambda _: None)
    assert client.calls == 1
    assert caught.value.status_code == status


@pytest.mark.parametrize("status", [403, 429])
def test_blocked_or_rate_limited_request_is_not_retried(status):
    class ApiError(Exception):
        code = status

    class FakeClassifier:
        calls = 0

        def classify(self, menus):
            self.calls += 1
            raise ApiError("stop")

    client = FakeClassifier()
    with pytest.raises(ClassificationBatchError):
        classify_with_bounded_retry(client, [{"id": 1}], sleep=lambda _: None)
    assert client.calls == 1


def test_frozen_fixture_is_backed_by_pilot_source_rows():
    root = Path(__file__).resolve().parents[2]
    plan = json.loads((root / "AI_Answer/serving_model_v2_pilot_plan.json").read_text())
    fixture = json.loads((root / "AI_Answer/menu_budget_classifier_v2_fixture.json").read_text())
    rows = {
        (int(restaurant["restaurantId"]), int(menu["id"])): menu
        for restaurant in plan["inputs"]
        for menu in restaurant["menus"]
    }
    assert fixture["frozenBeforeGeminiCall"] is True
    for case in fixture["cases"]:
        row = rows[(case["restaurantId"], case["menuId"])]
        assert row.get("name")
        assert row.get("priceValue") is not None


def test_retry_checkpoint_reuses_only_exact_success_and_refuses_terminal_resume():
    from scripts.run_gemini_menu_budget_retry import (
        reusable_chunk,
        validate_resume_checkpoint,
    )

    plan = {
        "model": "gemini-3.8-flash",
        "sourceSha256": "source",
        "fixtureSha256": "fixture",
    }
    checkpoint = {
        "runId": "gemini-menu-budget-v2-retry-1",
        "model": plan["model"],
        "sourceSha256": plan["sourceSha256"],
        "fixtureSha256": plan["fixtureSha256"],
        "terminalStop": None,
        "restaurantResults": {
            "9617": {
                "chunks": {
                    "0": {
                        "status": "SUCCESS",
                        "menuIds": [1, 2],
                        "classifications": [{"menuId": 1}, {"menuId": 2}],
                    }
                }
            }
        },
    }
    validate_resume_checkpoint(checkpoint, plan)
    assert reusable_chunk(checkpoint, 9617, 0, [1, 2])
    assert not reusable_chunk(checkpoint, 9617, 0, [1, 3])
    checkpoint["terminalStop"] = 429
    with pytest.raises(SystemExit, match="terminal"):
        validate_resume_checkpoint(checkpoint, plan)
