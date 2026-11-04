//! Atlas: multi-tenant shard placement, hot-shard detection, and rebalance planning
//! over a fixed hash-slot space. Integer arithmetic only, so every language port agrees
//! byte-for-byte (see conformance/).

use std::collections::HashMap;

/// Fixed hash-slot count, like Redis Cluster's 16384.
pub const SLOTS: usize = 16384;

const FNV64_OFFSET: u64 = 0xCBF2_9CE4_8422_2325;
const FNV64_PRIME: u64 = 0x0000_0100_0000_01B3;

pub fn fnv1a_64(s: &str) -> u64 {
    let mut h = FNV64_OFFSET;
    for b in s.as_bytes() {
        h ^= *b as u64;
        h = h.wrapping_mul(FNV64_PRIME);
    }
    h
}

pub fn slot_for(tenant: &str) -> usize {
    (fnv1a_64(tenant) % SLOTS as u64) as usize
}

/// A slot-range reassignment: [start, end) moves from `from` to `to`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Move {
    pub start: usize,
    pub end: usize,
    pub from: String,
    pub to: String,
}

pub struct ShardRouter {
    shards: Vec<String>,
    owner: Vec<usize>,
}

impl ShardRouter {
    pub fn new(shards: &[&str]) -> Self {
        assert!(!shards.is_empty(), "need at least one shard");
        let n = shards.len();
        let mut owner = vec![0usize; SLOTS];
        let base = SLOTS / n;
        let rem = SLOTS % n;
        let mut slot = 0;
        for (shard_idx, _) in shards.iter().enumerate() {
            let size = base + usize::from(shard_idx < rem);
            for _ in 0..size {
                owner[slot] = shard_idx;
                slot += 1;
            }
        }
        Self {
            shards: shards.iter().map(|s| s.to_string()).collect(),
            owner,
        }
    }

    pub fn shard_for(&self, tenant: &str) -> &str {
        &self.shards[self.owner[slot_for(tenant)]]
    }

    pub fn slot_owner(&self, slot: usize) -> &str {
        &self.shards[self.owner[slot]]
    }

    pub fn shards(&self) -> &[String] {
        &self.shards
    }
}

/// Shards over the mean by more than `overload_pct` percent, hottest-first (ties by name).
pub fn hot_shards(load: &HashMap<String, i64>, overload_pct: i64) -> Vec<String> {
    if load.is_empty() {
        return vec![];
    }
    let n = load.len() as i64;
    let total: i64 = load.values().sum();
    let threshold_num = total * (100 + overload_pct);
    let mut hot: Vec<String> = load
        .iter()
        .filter(|&(_, &v)| v * 100 * n > threshold_num)
        .map(|(s, _)| s.clone())
        .collect();
    hot.sort_by(|a, b| load[b].cmp(&load[a]).then_with(|| a.cmp(b)));
    hot
}

/// Move slots from each hot shard to the coldest receivers, filling one receiver to the
/// ceiling before the next, so moves are clean contiguous ranges.
pub fn plan_rebalance(
    router: &ShardRouter,
    load: &HashMap<String, i64>,
    overload_pct: i64,
) -> Vec<Move> {
    let hot = hot_shards(load, overload_pct);
    if hot.is_empty() {
        return vec![];
    }

    let mut working = load.clone();
    let n = router.shards.len() as i64;
    let total: i64 = load.values().sum();
    let ceiling = (total * (100 + overload_pct)) / (100 * n);

    let mut owned: HashMap<String, Vec<usize>> = HashMap::new();
    for s in &router.shards {
        owned.insert(s.clone(), Vec::new());
    }
    for slot in 0..SLOTS {
        owned.get_mut(router.slot_owner(slot)).unwrap().push(slot);
    }

    let mut moves: Vec<Move> = Vec::new();
    for donor in &hot {
        let mut receivers: Vec<String> = router
            .shards
            .iter()
            .filter(|s| *s != donor)
            .cloned()
            .collect();
        receivers.sort_by(|a, b| working[a].cmp(&working[b]).then_with(|| a.cmp(b)));
        for recv in receivers {
            while working[donor] > ceiling && working[&recv] < ceiling && !owned[donor].is_empty() {
                let slot = owned.get_mut(donor).unwrap().pop().unwrap();
                moves.push(Move {
                    start: slot,
                    end: slot + 1,
                    from: donor.clone(),
                    to: recv.clone(),
                });
                *working.get_mut(donor).unwrap() -= 1;
                *working.get_mut(&recv).unwrap() += 1;
            }
            if working[donor] <= ceiling {
                break;
            }
        }
    }

    moves.sort_by_key(|m| m.start);
    let mut coalesced: Vec<Move> = Vec::new();
    for m in moves {
        if let Some(last) = coalesced.last_mut()
            && m.start == last.end
            && m.from == last.from
            && m.to == last.to
        {
            last.end = m.end;
            continue;
        }
        coalesced.push(m);
    }
    coalesced
}
