// Atlas: multi-tenant shard placement, hot-shard detection, and rebalance planning over
// a fixed hash-slot space. Integer arithmetic (BigInt for the hash) so every language
// port agrees byte-for-byte (see conformance/).

export const SLOTS = 16384;

const FNV64_OFFSET = 0xcbf29ce484222325n;
const FNV64_PRIME = 0x100000001b3n;
const MASK64 = 0xffffffffffffffffn;

export function fnv1a64(s: string): bigint {
  let h = FNV64_OFFSET;
  for (const b of new TextEncoder().encode(s)) {
    h ^= BigInt(b);
    h = (h * FNV64_PRIME) & MASK64;
  }
  return h;
}

export function slotFor(tenant: string): number {
  return Number(fnv1a64(tenant) % BigInt(SLOTS));
}

export interface Move {
  start: number;
  end: number;
  from: string;
  to: string;
}

export class ShardRouter {
  private owner: number[];
  constructor(private shardList: string[]) {
    if (shardList.length === 0) throw new Error("need at least one shard");
    const n = shardList.length;
    this.owner = new Array<number>(SLOTS);
    const base = Math.floor(SLOTS / n);
    const rem = SLOTS % n;
    let slot = 0;
    for (let shardIdx = 0; shardIdx < n; shardIdx++) {
      const size = base + (shardIdx < rem ? 1 : 0);
      for (let i = 0; i < size; i++) this.owner[slot++] = shardIdx;
    }
  }
  shardFor(tenant: string): string {
    return this.shardList[this.owner[slotFor(tenant)]];
  }
  slotOwner(slot: number): string {
    return this.shardList[this.owner[slot]];
  }
  get shards(): string[] {
    return this.shardList;
  }
}

export function hotShards(load: Record<string, number>, overloadPct: number): string[] {
  const keys = Object.keys(load);
  if (keys.length === 0) return [];
  const n = keys.length;
  const total = keys.reduce((a, k) => a + load[k], 0);
  const thresholdNum = total * (100 + overloadPct);
  return keys
    .filter((k) => load[k] * 100 * n > thresholdNum)
    .sort((a, b) => (load[b] - load[a]) || (a < b ? -1 : 1));
}

export function planRebalance(
  router: ShardRouter,
  load: Record<string, number>,
  overloadPct: number,
): Move[] {
  const hot = hotShards(load, overloadPct);
  if (hot.length === 0) return [];

  const working: Record<string, number> = { ...load };
  const n = router.shards.length;
  const total = Object.values(load).reduce((a, b) => a + b, 0);
  const ceiling = Math.floor((total * (100 + overloadPct)) / (100 * n));

  const owned: Record<string, number[]> = {};
  for (const s of router.shards) owned[s] = [];
  for (let slot = 0; slot < SLOTS; slot++) owned[router.slotOwner(slot)].push(slot);

  const moves: Move[] = [];
  for (const donor of hot) {
    const receivers = router.shards
      .filter((s) => s !== donor)
      .sort((a, b) => (working[a] - working[b]) || (a < b ? -1 : 1));
    for (const recv of receivers) {
      while (working[donor] > ceiling && working[recv] < ceiling && owned[donor].length > 0) {
        const slot = owned[donor].pop()!;
        moves.push({ start: slot, end: slot + 1, from: donor, to: recv });
        working[donor]--;
        working[recv]++;
      }
      if (working[donor] <= ceiling) break;
    }
  }

  moves.sort((a, b) => a.start - b.start);
  const coalesced: Move[] = [];
  for (const m of moves) {
    const last = coalesced[coalesced.length - 1];
    if (last && m.start === last.end && m.from === last.from && m.to === last.to) {
      last.end = m.end;
      continue;
    }
    coalesced.push({ ...m });
  }
  return coalesced;
}
