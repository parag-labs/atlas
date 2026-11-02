"""The Python reference must reproduce the committed conformance vectors exactly."""

from __future__ import annotations

import json
from pathlib import Path

from atlas import ShardRouter, fnv1a_64, hot_shards, plan_rebalance, slot_for

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "conformance" / "vectors.json").read_text(
        encoding="utf-8"
    )
)


def test_hash_probes():
    for probe, expected in VECTORS["hash"].items():
        assert fnv1a_64(probe) == int(expected, 16)


def test_placement_matches():
    r = ShardRouter(VECTORS["shards"])
    for tenant, shard in VECTORS["placement"].items():
        assert r.shard_for(tenant) == shard


def test_slot_for_matches():
    for tenant, slot in VECTORS["slot_for"].items():
        assert slot_for(tenant) == slot


def test_hot_matches():
    spec = VECTORS["hot"]
    assert hot_shards(spec["load"], spec["overload_pct"]) == spec["result"]


def test_rebalance_matches():
    spec = VECTORS["rebalance"]
    r = ShardRouter(VECTORS["shards"])
    plan = plan_rebalance(r, spec["load"], spec["overload_pct"]).to_list()
    assert plan == spec["plan"]
