"""Unit tests for the action mini-DSL parser used by `GoapPlanner.from_action_lib`."""

from __future__ import annotations

from app.agents.decision.goap_dsl import (
    compile_effect,
    compile_precondition,
    compile_predicate,
    compile_transformer,
)


def test_compare_int_ge():
    check = compile_precondition("agent.energy", ">= 1", params={})
    assert check({"energy": 3}) is True
    assert check({"energy": 1}) is True
    assert check({"energy": 0}) is False


def test_compare_neq_with_param():
    check = compile_precondition(
        "agent.location_uid", "!= target_uid", params={"target_uid": "lib"}
    )
    assert check({"location_uid": "dorm"}) is True
    assert check({"location_uid": "lib"}) is False


def test_compare_path_to_path():
    check = compile_precondition(
        "item.location_uid", "== agent.location_uid", params={}
    )
    assert check({"location_uid": "dorm", "item.location_uid": "dorm"}) is True
    assert check({"location_uid": "dorm", "item.location_uid": "lab"}) is False


def test_effect_assignment():
    eff = compile_effect("agent.location_uid", "= target_uid", params={"target_uid": "lib"})
    state = {"location_uid": "dorm", "energy": 3}
    out = eff(state)
    assert out["location_uid"] == "lib"
    assert out["energy"] == 3
    # Original not mutated
    assert state["location_uid"] == "dorm"


def test_effect_increment_and_decrement():
    inc = compile_effect("agent.energy", "+= 1", params={})
    dec = compile_effect("agent.energy", "-= 2", params={})
    out = inc({"energy": 3})
    assert out["energy"] == 4
    out2 = dec({"energy": 3})
    assert out2["energy"] == 1


def test_compile_predicate_combines_all_checks():
    pred = compile_predicate(
        {"agent.energy": ">= 1", "agent.location_uid": "!= target_uid"},
        params={"target_uid": "lib"},
    )
    assert pred({"energy": 2, "location_uid": "dorm"}) is True
    assert pred({"energy": 0, "location_uid": "dorm"}) is False
    assert pred({"energy": 2, "location_uid": "lib"}) is False


def test_compile_transformer_applies_in_order():
    transform = compile_transformer(
        {"agent.location_uid": "= target_uid", "agent.energy": "-= 1"},
        params={"target_uid": "lib"},
    )
    out = transform({"location_uid": "dorm", "energy": 3})
    assert out == {"location_uid": "lib", "energy": 2}
