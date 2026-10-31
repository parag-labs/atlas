# atlas

A multi-tenant data platform's placement core: deterministic **tenant → shard**
mapping over a fixed hash-slot space, **hot-shard detection**, and **rebalance
planning** — implemented in **six languages** with identical output, proven
byte-for-byte by shared golden vectors. Plus an interactive shard-map visualizer.

[![Continuous integration](https://github.com/parag-labs/atlas/actions/workflows/tests.yml/badge.svg)](https://github.com/parag-labs/atlas/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3670A0?style=flat-square&logo=python&logoColor=ffdd54)
![Go](https://img.shields.io/badge/Go-00ADD8?style=flat-square&logo=go&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-000000?style=flat-square&logo=rust&logoColor=white)
![C#](https://img.shields.io/badge/C%23-512BD4?style=flat-square&logo=dotnet&logoColor=white)
![Java](https://img.shields.io/badge/Java-ED8B00?style=flat-square&logo=openjdk&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)

**▶ [Live visualizer](https://parag-labs.github.io/atlas/)** — push a shard's load up,
watch Atlas flag it hot and compute the exact slot ranges to move.

![shard map](docs/shard-map.png)

![architecture](docs/diagrams/architecture.png)

*The one-page architecture — placement, the fixed slot layer, and rebalance. Source SVG: [docs/diagrams/architecture.svg](docs/diagrams/architecture.svg).*

## Why

When you spread thousands of tenants across a fixed set of shards, three decisions have
to be **identical in every service** that touches the cluster, or two services disagree
about where a tenant's data lives:

1. **Which shard owns a tenant?** Hash the tenant into one of a fixed number of *hash
   slots* (like Redis Cluster's 16384), and give each shard a contiguous slot range.
   Slots decouple tenants from shards — moving a tenant is moving a slot's owner, and
   rebalancing is reassigning slot ranges, never rehashing every tenant.
2. **Which shards are hot?** Given per-shard load, which exceed their fair share past a
   threshold — the trigger for a migration.
3. **How do we rebalance?** A deterministic set of slot-range moves that relieves the
   hot shards, so every service computes the *same* plan.

## The design in one place

```python
from atlas import ShardRouter, hot_shards, plan_rebalance

router = ShardRouter(["shard-0", "shard-1", "shard-2"])
router.shard_for("tenant-42")          # -> deterministic owning shard

load = {"shard-0": 900, "shard-1": 50, "shard-2": 50}
hot_shards(load, overload_pct=20)      # -> ["shard-0"]
plan_rebalance(router, load, 20)       # -> contiguous slot-range moves off shard-0
```

Placement, detection, and the plan are **integer arithmetic over a fixed 16384-slot
space** — FNV-1a → slot, even contiguous ranges, thresholds compared by
cross-multiplication instead of division — so all six ports produce byte-for-byte
identical output. Details in [DESIGN.md](DESIGN.md) and
[architecture/ADR](architecture/ADR).

## Six languages, one behavior

| Language | Run | Conformance |
|----------|-----|:-----------:|
| Python | `cd python && PYTHONPATH=src pytest -q` | ✓ |
| Go | `cd go && go test ./...` | ✓ |
| Rust | `cd rust && cargo test` | ✓ |
| C# (.NET 10) | `cd csharp/tests && dotnet test` | ✓ |
| Java (17+) | `cd java && mvn test` | ✓ |
| TypeScript | `cd web && npm test` | ✓ |

Each port replays [conformance/vectors.json](conformance/) — the slot for each tenant,
the owning shard, the hot-shard list, and the exact rebalance plan — and asserts it
matches. If any language disagrees, CI fails.

## Numbers

Measured (`python bench/benchmark.py`), detail in [BENCHMARKS.md](BENCHMARKS.md):
~300,000 placements/sec in pure Python, and a rebalance plan for a hot shard in a
16-shard cluster computed in ~4ms — moving 1024 slots expressed as just **3 contiguous
range moves**, because the planner fills one receiver before the next.

## Layout

```
atlas/
├── python/         reference implementation + pytest
├── go/ rust/ csharp/ java/   ports, each with a conformance test
├── web/            TypeScript core + the shard-map visualizer (Vite/React)
├── conformance/    golden vectors + generator; the cross-language contract
├── bench/          placement throughput + rebalance cost
├── architecture/   ADRs
├── docs/           architecture diagram (svg + png)
├── DESIGN.md       slots, placement, hot detection, the rebalance planner
└── BENCHMARKS.md   reproducible numbers
```

Part of [parag-labs](https://github.com/parag-labs).
