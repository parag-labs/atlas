"""Benchmark Atlas: placement throughput and rebalance-plan cost. Measured on this
machine, reproducible: python bench/benchmark.py"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from atlas import ShardRouter, plan_rebalance

RESULTS = ROOT / "bench" / "results"
RESULTS.mkdir(exist_ok=True)


def placement_throughput() -> int:
    router = ShardRouter([f"shard-{i}" for i in range(16)])
    tenants = [f"tenant-{i}" for i in range(200000)]
    start = time.perf_counter()
    for t in tenants:
        router.shard_for(t)
    elapsed = time.perf_counter() - start
    return int(len(tenants) / elapsed)


def rebalance_cost() -> dict:
    # A cluster where one shard is very hot; how long to compute the plan.
    router = ShardRouter([f"shard-{i}" for i in range(16)])
    load = {f"shard-{i}": 100 for i in range(16)}
    load["shard-0"] = 5000
    start = time.perf_counter()
    plan = plan_rebalance(router, load, 20)
    elapsed = time.perf_counter() - start
    moved = sum(m[1] - m[0] for m in plan.moves)
    return {
        "shards": 16,
        "plan_moves": len(plan.moves),
        "slots_moved": moved,
        "plan_ms": round(elapsed * 1000, 3),
    }


def main() -> None:
    summary = {
        "placement_per_sec": placement_throughput(),
        "rebalance": rebalance_cost(),
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
