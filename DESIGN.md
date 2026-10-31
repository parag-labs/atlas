# atlas: design notes

Status: accepted
Author: Parag Sawant

## Goals

A multi-tenant platform routes every request to the shard holding that tenant's data,
so placement must be fast, stable, and — critically — *the same everywhere*. Three
decisions, all deterministic and portable across languages:

1. Tenant → shard placement.
2. Which shards are hot (over their fair share).
3. How to rebalance a hot shard with minimal, clean data movement.

## Key decision: a fixed hash-slot layer

The naive approach is `hash(tenant) % shard_count`. It's simple and it's the classic
trap: change `shard_count` and almost every tenant remaps, so scaling the cluster
reshuffles everything.

Atlas inserts a fixed layer of **16384 hash slots** between tenants and shards (the same
count Redis Cluster uses). Tenants hash to a slot; shards own contiguous *ranges* of
slots. The slot count never changes, so:

- Adding a shard reassigns some slot ranges to it — only the tenants in those slots
  move, not the whole keyspace.
- A tenant's slot is stable for the life of the cluster; only which shard owns that slot
  changes, and that's an explicit, planned operation.

Ranges (rather than the scattered virtual-node placement of a hash ring) are the right
choice here because a migration moves *ranges* of data, and a contiguous range is one
efficient bulk copy instead of thousands of scattered keys.

## Integer-only, for portability

Every decision is integer arithmetic so the six ports agree byte-for-byte:

- **Placement** — FNV-1a 64-bit of the tenant id, `% 16384`, then an array lookup of the
  slot's owner. FNV is used (not each language's string hash) because it's identical
  everywhere.
- **Even ranges** — `16384 / n` slots each, with the first `16384 % n` shards getting one
  extra, so the total is exactly 16384 and the split is as even as integers allow.
- **Hot detection** — a shard is hot iff `load * 100 * n > total * (100 + pct)`, the
  overload test with the division cleared by multiplying through.
- **Rebalance** — the per-shard ceiling is `total * (100 + pct) / (100 * n)` (integer),
  and the planner sheds the hot shard's highest slots to the coldest receiver, filling
  each receiver to the ceiling before the next. Filling one at a time is what keeps the
  moves as a few contiguous ranges.

## Non-goals

- **Not the data plane.** Atlas decides *where* a tenant lives and *how* to rebalance; it
  doesn't store data, run the copy, or cut over traffic. It's the placement logic a real
  migration system would call.
- **Not weighted shards.** Every shard gets an equal slot range. Heterogeneous shard
  sizes (a bigger box gets more slots) are a natural extension, left out to keep the
  contract simple.
- **Load is an input, not measured here.** Atlas takes a load snapshot and acts on it;
  collecting real per-shard load is the platform's job.
