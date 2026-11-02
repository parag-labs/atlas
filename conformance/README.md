# Cross-language conformance

A multi-tenant cluster only works if every service agrees on where each tenant lives
and how to rebalance a hot shard. This directory pins that agreement.

## What's here

- **`vectors.json`** — for a fixed set of shards and tenants: the slot each tenant
  hashes to, the shard that owns it, which shards are hot for a given load snapshot, and
  the exact rebalance plan (slot-range moves) that relieves them.
- **`generate.py`** — regenerates the vectors from the Python reference.

## The contract

Each language port replays these and asserts identical results. Placement, hot-shard
detection, and the rebalance plan are all **integer arithmetic over a fixed 16384-slot
space** (FNV-1a 64-bit → slot, even contiguous slot ranges per shard, threshold and
ceiling compared by cross-multiplication instead of division), so every port produces
byte-for-byte identical output. If any disagrees, CI fails.

| Port | Conformance test |
|------|------------------|
| Python | `python/tests/test_conformance.py` |
| Go | `go/conformance_test.go` |
| Rust | `rust/tests/conformance.rs` |
| C# | `csharp/tests/ConformanceTests.cs` |
| Java | `java/.../ConformanceTest.java` |
| TypeScript | `web/src/core/conformance.test.ts` |
