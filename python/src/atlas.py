"""Atlas: multi-tenant shard placement, hot-shard detection, and rebalance planning.

A multi-tenant data platform spreads many tenants across a fixed set of shards. Three
decisions have to be deterministic and identical across every service that touches the
cluster, or two services will disagree about where a tenant's data lives:

* **Placement** — which shard owns a tenant. Atlas hashes the tenant id into a fixed
  number of *hash slots* (like Redis Cluster's 16384 slots), and each shard owns a
  contiguous range of slots. Slots decouple tenants from shards: moving a tenant is
  moving its slot's ownership, and rebalancing is reassigning slot ranges, without
  rehashing every tenant.
* **Hot-shard detection** — given per-shard load, which shards exceed their fair share
  by more than a threshold. This is the trigger for a migration.
* **Rebalance planning** — a deterministic set of slot moves that relieves the hot
  shards, so every service computes the *same* plan from the same inputs.

Everything here is integer arithmetic over a fixed slot count, so the Python, Go, Rust,
C#, Java, and TypeScript ports place every tenant on the same shard and produce the
same rebalance plan — pinned by the conformance vectors.
"""

from __future__ import annotations

SLOTS = 16384

FNV64_OFFSET = 0xCBF29CE484222325
FNV64_PRIME = 0x100000001B3
MASK64 = 0xFFFFFFFFFFFFFFFF


def fnv1a_64(data: str) -> int:
    h = FNV64_OFFSET
    for byte in data.encode("utf-8"):
        h ^= byte
        h = (h * FNV64_PRIME) & MASK64
    return h


def slot_for(tenant_id: str) -> int:
    """The hash slot a tenant maps to, in [0, SLOTS)."""
    return fnv1a_64(tenant_id) % SLOTS


class ShardRouter:
    """Maps tenants to shards via a fixed slot space. Shards own contiguous slot ranges
    assigned as evenly as possible; the assignment is deterministic in the shard order."""

    def __init__(self, shards: list[str]) -> None:
        if not shards:
            raise ValueError("need at least one shard")
        self.shards = list(shards)
        self._owner = self._assign_ranges(len(shards))

    def _assign_ranges(self, n: int) -> list[int]:
        """Return a list of length SLOTS mapping slot -> shard index, split into n
        near-equal contiguous ranges (slot // ceil(SLOTS/n))."""
        owner = [0] * SLOTS
        base = SLOTS // n
        rem = SLOTS % n
        slot = 0
        for shard_idx in range(n):
            # The first `rem` shards get one extra slot so the total is exactly SLOTS.
            size = base + (1 if shard_idx < rem else 0)
            for _ in range(size):
                owner[slot] = shard_idx
                slot += 1
        return owner

    def shard_for(self, tenant_id: str) -> str:
        return self.shards[self._owner[slot_for(tenant_id)]]

    def slot_owner(self, slot: int) -> str:
        return self.shards[self._owner[slot]]


def hot_shards(load: dict[str, int], overload_pct: int) -> list[str]:
    """Shards whose load exceeds the mean by more than ``overload_pct`` percent, sorted
    by descending load then name. Integer comparison: load*100 > mean_load*(100+pct),
    where mean_load is expressed as total*1 / n to avoid a division."""
    if not load:
        return []
    n = len(load)
    total = sum(load.values())
    # load > mean * (1 + pct/100)  <=>  load * 100 * n > total * (100 + pct)
    threshold_num = total * (100 + overload_pct)
    hot = [s for s, v in load.items() if v * 100 * n > threshold_num]
    hot.sort(key=lambda s: (-load[s], s))
    return hot


class RebalancePlan:
    """A deterministic set of slot-range moves that relieves hot shards by handing some
    of their slots to the least-loaded shards. The plan is computed purely from the
    shard order, the current load, and the overload threshold, so every service derives
    the identical plan."""

    def __init__(self, moves: list[tuple[int, int, str, str]]) -> None:
        # each move: (slot_start, slot_end_exclusive, from_shard, to_shard)
        self.moves = moves

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RebalancePlan) and self.moves == other.moves

    def to_list(self) -> list[dict]:
        return [
            {"start": s, "end": e, "from": f, "to": t} for (s, e, f, t) in self.moves
        ]


def plan_rebalance(router: ShardRouter, load: dict[str, int], overload_pct: int) -> RebalancePlan:
    """Move slots from each hot shard to the coldest shards until no shard is over the
    threshold. Deterministic: hot shards processed hottest-first; each donor sheds its
    highest slots to the coldest receiver, filling that receiver up to the ceiling
    before moving to the next. Filling one receiver at a time keeps the moves as clean
    contiguous ranges."""
    hot = hot_shards(load, overload_pct)
    if not hot:
        return RebalancePlan([])

    working = dict(load)
    n = len(router.shards)
    total = sum(load.values())
    # Target ceiling per shard, integer: mean * (1 + pct/100), rounded down.
    ceiling = (total * (100 + overload_pct)) // (100 * n)

    # Slots currently owned by each shard, ascending; we shed from the high end.
    owned: dict[str, list[int]] = {s: [] for s in router.shards}
    for slot in range(SLOTS):
        owned[router.slot_owner(slot)].append(slot)

    moves: list[tuple[int, int, str, str]] = []
    for donor in hot:
        # Receivers ranked coldest-first once, up front; fill each to the ceiling.
        receivers = sorted(
            (s for s in router.shards if s != donor),
            key=lambda s: (working[s], s),
        )
        for recv in receivers:
            while working[donor] > ceiling and working[recv] < ceiling and owned[donor]:
                slot = owned[donor].pop()
                moves.append((slot, slot + 1, donor, recv))
                working[donor] -= 1
                working[recv] += 1
            if working[donor] <= ceiling:
                break

    # Coalesce adjacent single-slot moves with the same donor/receiver into ranges.
    moves.sort()
    coalesced: list[tuple[int, int, str, str]] = []
    for m in moves:
        if coalesced:
            ps, pe, pf, pt = coalesced[-1]
            if m[0] == pe and m[2] == pf and m[3] == pt:
                coalesced[-1] = (ps, m[1], pf, pt)
                continue
        coalesced.append(m)
    return RebalancePlan(coalesced)
