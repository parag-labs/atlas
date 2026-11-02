"""Generate conformance/vectors.json for Atlas. Run from repo root:
python conformance/generate.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from atlas import ShardRouter, fnv1a_64, hot_shards, plan_rebalance, slot_for

SHARDS = ["shard-0", "shard-1", "shard-2", "shard-3"]
TENANTS = [f"tenant-{i}" for i in range(40)]
HASH_PROBES = ["", "a", "foobar", "tenant-0", "shard-0"]

# A load snapshot with one clearly hot shard, for the detection + rebalance vectors.
LOAD = {"shard-0": 800, "shard-1": 120, "shard-2": 130, "shard-3": 150}
OVERLOAD_PCT = 20


def build() -> dict:
    router = ShardRouter(SHARDS)
    return {
        "_comment": "Atlas cross-language conformance vectors. See conformance/README.md.",
        "slots": 16384,
        "hash": {p: f"0x{fnv1a_64(p):016X}" for p in HASH_PROBES},
        "shards": SHARDS,
        "placement": {t: router.shard_for(t) for t in TENANTS},
        "slot_for": {t: slot_for(t) for t in TENANTS},
        "hot": {
            "load": LOAD,
            "overload_pct": OVERLOAD_PCT,
            "result": hot_shards(LOAD, OVERLOAD_PCT),
        },
        "rebalance": {
            "load": LOAD,
            "overload_pct": OVERLOAD_PCT,
            "plan": plan_rebalance(router, LOAD, OVERLOAD_PCT).to_list(),
        },
    }


def main() -> None:
    out = ROOT / "conformance" / "vectors.json"
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
