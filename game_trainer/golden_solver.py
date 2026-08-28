from __future__ import annotations

from typing import Any


def verify_golden_result(
    request: dict[str, Any],
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerances: dict[str, float],
) -> list[str]:
    errors: list[str] = []
    if actual.get("event") != "complete":
        errors.append(f"expected complete event, got {actual.get('event')!r}")
        return errors
    for key in ("configHash", "iterations"):
        if actual.get(key) != expected.get(key):
            errors.append(f"{key}: expected {expected.get(key)!r}, got {actual.get(key)!r}")
    for key, tolerance_key in (
        ("exploitability", "exploitability"),
        ("oopEv", "value"),
        ("ipEv", "value"),
    ):
        difference = abs(float(actual.get(key, float("inf"))) - float(expected[key]))
        if difference > tolerances[tolerance_key]:
            errors.append(f"{key}: difference {difference} exceeds {tolerances[tolerance_key]}")

    actual_actions = {item["action"]: float(item["probability"]) for item in actual.get("actions", [])}
    expected_actions = expected["actions"]
    if set(actual_actions) != set(expected_actions):
        errors.append(f"actions: expected {sorted(expected_actions)}, got {sorted(actual_actions)}")
    else:
        for action, probability in expected_actions.items():
            difference = abs(actual_actions[action] - float(probability))
            if difference > tolerances["probability"]:
                errors.append(
                    f"{action} probability: difference {difference} exceeds {tolerances['probability']}"
                )

    probability_sum = sum(actual_actions.values())
    if abs(probability_sum - 1.0) > tolerances["probability"]:
        errors.append(f"action probabilities sum to {probability_sum}, not 1")
    value_sum = float(actual.get("oopEv", 0)) + float(actual.get("ipEv", 0))
    if abs(value_sum - request["startingPot"]) > tolerances["value"]:
        errors.append(f"seat EVs sum to {value_sum}, expected pot {request['startingPot']}")
    return errors
