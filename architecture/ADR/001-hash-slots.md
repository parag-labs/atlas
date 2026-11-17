# ADR-001: A fixed hash-slot layer between tenants and shards

Status: accepted
Author: Parag Sawant

## Context

Every request in a multi-tenant platform has to be routed to the shard holding that
tenant's data. The mapping from tenant to shard is the most-called decision in the whole
system, and it has to survive the cluster growing and shrinking without reshuffling
everyone's data.

The options:

- **`hash(tenant) % shard_count`.** One line, O(1). But the shard count is baked into
  the result, so adding a shard remaps almost every tenant — a full data reshuffle to
  scale out.
- **A consistent-hash ring.** Adding a shard moves only ~1/N of tenants. But a shard's
  tenants are scattered across the ring, so a migration moves thousands of
  non-contiguous keys.
- **A fixed slot layer** (Redis Cluster's approach). A fixed number of hash slots
  (16384) sits between tenants and shards; tenants hash to a slot, shards own contiguous
  slot ranges.

## Decision

Use a **fixed 16384-slot layer**, with each shard owning contiguous slot ranges.

## Why

- **Scaling doesn't reshuffle.** The slot count is constant, so a tenant's slot never
  changes. Adding a shard reassigns some slot *ranges*; only the tenants in those slots
  move.
- **Migrations move ranges, not scattered keys.** Because a shard owns contiguous slot
  ranges, relieving a hot shard is a handful of range moves — each a bulk copy — instead
  of thousands of individual key moves the way a hash ring would produce.
- **Placement stays O(1).** Hash to a slot, look up the slot's owner in an array. As fast
  as modulo, without modulo's reshuffle problem.
- **It's a proven design.** Redis Cluster runs exactly this at scale, which is a strong
  signal it's the right shape.

## Trade-offs

- **A slot is the smallest unit of movement.** 16384 slots over N shards means placement
  granularity is `16384 / N` — plenty for realistic cluster sizes, but you can't move a
  single tenant without moving its whole slot. Acceptable: tenants are meant to share
  slots, and per-tenant migration is a different (rarer) operation.
- **Even ranges, not weighted.** Every shard gets an equal share of slots. Heterogeneous
  shards would need weighted range sizes — a deliberate non-goal here.

## Consequences

Rebalancing (ADR-002 territory) becomes "reassign slot ranges from hot shards to cold
ones," which the planner does deterministically and compactly. The slot layer is the
foundation every other Atlas decision builds on.
