# Benchmarks

Measured on this machine, reproducible: `python bench/benchmark.py`.

## Placement throughput

| Metric | Value |
|--------|------:|
| Tenants placed | 200,000 |
| Throughput | ~300,000 placements/sec |

Placement is one FNV-1a hash, a modulo into the slot space, and an array lookup for the
slot's owner — O(1), and the array lookup keeps it cache-friendly. In a compiled port
(Go/Rust) this is several times faster; the pure-Python number is the floor.

## Rebalance planning

A 16-shard cluster with one shard at 5000 load and the rest at 100:

| Metric | Value |
|--------|------:|
| Shards | 16 |
| Slots moved | 1,024 |
| Plan size | **3 moves** |
| Time to plan | ~4 ms |

The interesting number is **3 moves for 1,024 slots**. The planner fills one receiver to
the ceiling before moving to the next, so the slots it sheds from the hot shard land as
a few contiguous ranges instead of thousands of single-slot moves. That matters
operationally: a migration executes range moves, and three of them is a very different
thing to schedule than a thousand.

## Reading these together

Placement is cheap and constant-time; the cost concentrates in rebalancing, which is
rare (only when a shard goes hot) and produces a compact plan. That's the shape you want
in a control plane — the hot path (routing every request) is trivial, and the expensive
work (moving data) is infrequent and minimized.
