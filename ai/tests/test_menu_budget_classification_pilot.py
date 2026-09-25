from __future__ import annotations

import json

import pytest

from app.menu_budget_classification_pilot import make_plan, validate_output


def test_valid_existing_menu_ids_are_preserved_and_omissions_fail_closed():
    menus = [{"id": 7}, {"id": 8}]
    raw = json.dumps(
        {
            "classifications": [
                {"menuId": 7, "budgetRole": "MEAL_CANDIDATE", "reason": "single meal"},
            ]
        }
    )

    result = validate_output(raw, menus)

    assert [row["menuId"] for row in result["classifications"]] == [7, 8]
    assert result["classifications"][1]["budgetRole"] == "UNKNOWN"


@pytest.mark.parametrize(
    "rows",
    [
        [{"menuId": 99, "budgetRole": "SIDE", "reason": "x"}],
        [
            {"menuId": 7, "budgetRole": "SIDE", "reason": "x"},
            {"menuId": 7, "budgetRole": "DRINK", "reason": "y"},
        ],
        [{"menuId": 7, "budgetRole": "FOOD", "reason": "x"}],
    ],
)
def test_unknown_duplicate_or_invalid_classification_is_rejected(rows):
    with pytest.raises(ValueError):
        validate_output(json.dumps({"classifications": rows}), [{"id": 7}])


def test_plan_freezes_only_five_targets_and_hashes_inputs():
    plan = make_plan(
        [
            {"restaurantId": rid, "menus": [{"id": rid, "priceValue": 9000}]}
            for rid in (9617, 9571, 9568, 10042, 9559)
        ]
    )

    assert plan["targetsFrozen"] == [9617, 9571, 9568, 10042, 9559]
    assert plan["plannedQwenCalls"] == 5
    assert all(len(row["inputHash"]) == 64 for row in plan["restaurants"])
