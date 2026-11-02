"""Atlas core behaviour: deterministic placement, even slot distribution, hot-shard
detection, and a rebalance plan that actually relieves the hot shard."""

from __future__ import annotations

from collections import Counter

from atlas import (
    SLOTS,
    RebalancePlan,
    ShardRouter,
    fnv1a_64,
    hot_shards,
    plan_rebalance,
    slot_for,
)


def test_fnv_known_vectors():
    assert fnv1a_64("") == 0xCBF29CE484222325
    assert fnv1a_64("foobar") == 0x85944171F73967E8


def test_placement_is_stable():
    r = ShardRouter(["shard-a", "shard-b", "shard-c"])
    assert r.shard_for("tenant-42") == r.shard_for("tenant-42")


def test_every_tenant_maps_to_a_real_shard():
    shards = ["s0", "s1", "s2", "s3"]
    r = ShardRouter(shards)
    for i in range(2000):
        assert r.shard_for(f"tenant-{i}") in shards


def test_slots_are_evenly_divided():
    r = ShardRouter(["a", "b", "c", "d", "e"])
    counts = Counter(r.slot_owner(s) for s in range(SLOTS))
    # 16384 / 5 = 3276.8, so each shard owns 3276 or 3277 slots.
    assert max(counts.values()) - min(counts.values()) <= 1
    assert sum(counts.values()) == SLOTS


def test_slot_for_in_range():
    for i in range(1000):
        assert 0 <= slot_for(f"t{i}") < SLOTS


def test_hot_shards_detects_overload():
    load = {"a": 100, "b": 100, "c": 400}  # mean 200, c is 100% over
    assert hot_shards(load, overload_pct=25) == ["c"]
    # With no overload threshold exceeded, nothing is hot.
    assert hot_shards({"a": 100, "b": 110, "c": 90}, overload_pct=25) == []


def test_hot_shards_sorted_hottest_first():
    load = {"a": 500, "b": 100, "c": 400}  # mean ~333
    assert hot_shards(load, overload_pct=10) == ["a", "c"]


def test_rebalance_relieves_the_hot_shard():
    router = ShardRouter(["a", "b", "c"])
    # a is heavily overloaded.
    load = {"a": 900, "b": 50, "c": 50}
    plan = plan_rebalance(router, load, overload_pct=20)
    assert plan.moves, "expected a non-empty plan"
    # Every move must take slots from the hot shard.
    for _start, _end, frm, _to in plan.moves:
        assert frm == "a"
    # Applying the plan should reduce a's projected load below the pre-plan value.
    moved = sum(e - s for s, e, _f, _t in plan.moves)
    assert moved > 0


def test_rebalance_is_deterministic():
    router = ShardRouter(["a", "b", "c", "d"])
    load = {"a": 700, "b": 100, "c": 100, "d": 100}
    p1 = plan_rebalance(router, load, 20)
    p2 = plan_rebalance(router, load, 20)
    assert p1 == p2


def test_no_rebalance_when_balanced():
    router = ShardRouter(["a", "b", "c"])
    load = {"a": 100, "b": 100, "c": 100}
    assert plan_rebalance(router, load, 20) == RebalancePlan([])
