// Package atlas implements multi-tenant shard placement, hot-shard detection, and
// rebalance planning over a fixed hash-slot space. Every decision is integer
// arithmetic so the Python, Go, Rust, C#, Java, and TypeScript ports agree
// byte-for-byte (see conformance/).
package atlas

import "sort"

// Slots is the fixed hash-slot count, like Redis Cluster's 16384. Tenants hash into a
// slot; shards own contiguous slot ranges. Moving a tenant is moving a slot's owner.
const Slots = 16384

const (
	fnv64Offset uint64 = 0xCBF29CE484222325
	fnv64Prime  uint64 = 0x100000001B3
)

// Fnv1a64 hashes s with FNV-1a, shared across all ports.
func Fnv1a64(s string) uint64 {
	h := fnv64Offset
	for _, b := range []byte(s) {
		h ^= uint64(b)
		h *= fnv64Prime
	}
	return h
}

// SlotFor is the slot a tenant maps to, in [0, Slots).
func SlotFor(tenant string) int {
	return int(Fnv1a64(tenant) % Slots)
}

// ShardRouter maps tenants to shards via evenly divided contiguous slot ranges.
type ShardRouter struct {
	shards []string
	owner  []int // slot -> shard index
}

// NewShardRouter assigns the slot space into len(shards) near-equal contiguous ranges.
func NewShardRouter(shards []string) *ShardRouter {
	if len(shards) == 0 {
		panic("need at least one shard")
	}
	n := len(shards)
	owner := make([]int, Slots)
	base := Slots / n
	rem := Slots % n
	slot := 0
	for shardIdx := 0; shardIdx < n; shardIdx++ {
		size := base
		if shardIdx < rem {
			size++
		}
		for i := 0; i < size; i++ {
			owner[slot] = shardIdx
			slot++
		}
	}
	cp := make([]string, n)
	copy(cp, shards)
	return &ShardRouter{shards: cp, owner: owner}
}

func (r *ShardRouter) ShardFor(tenant string) string {
	return r.shards[r.owner[SlotFor(tenant)]]
}

func (r *ShardRouter) SlotOwner(slot int) string {
	return r.shards[r.owner[slot]]
}

func (r *ShardRouter) Shards() []string { return r.shards }

// HotShards returns shards whose load exceeds the mean by more than overloadPct percent,
// hottest-first (ties by name). Integer test: load*100*n > total*(100+pct).
func HotShards(load map[string]int, overloadPct int) []string {
	if len(load) == 0 {
		return []string{}
	}
	n := len(load)
	total := 0
	for _, v := range load {
		total += v
	}
	thresholdNum := total * (100 + overloadPct)
	hot := []string{}
	for s, v := range load {
		if v*100*n > thresholdNum {
			hot = append(hot, s)
		}
	}
	sort.Slice(hot, func(i, j int) bool {
		if load[hot[i]] != load[hot[j]] {
			return load[hot[i]] > load[hot[j]]
		}
		return hot[i] < hot[j]
	})
	return hot
}

// Move is a slot-range reassignment: [Start, End) goes from From to To.
type Move struct {
	Start int    `json:"start"`
	End   int    `json:"end"`
	From  string `json:"from"`
	To    string `json:"to"`
}

// PlanRebalance moves slots from each hot shard to the coldest receivers, filling one
// receiver to the ceiling before the next, so moves are clean contiguous ranges.
func PlanRebalance(r *ShardRouter, load map[string]int, overloadPct int) []Move {
	hot := HotShards(load, overloadPct)
	if len(hot) == 0 {
		return []Move{}
	}

	working := make(map[string]int, len(load))
	for k, v := range load {
		working[k] = v
	}
	n := len(r.shards)
	total := 0
	for _, v := range load {
		total += v
	}
	ceiling := (total * (100 + overloadPct)) / (100 * n)

	owned := make(map[string][]int, n)
	for _, s := range r.shards {
		owned[s] = []int{}
	}
	for slot := 0; slot < Slots; slot++ {
		s := r.SlotOwner(slot)
		owned[s] = append(owned[s], slot)
	}

	var moves []Move
	for _, donor := range hot {
		receivers := make([]string, 0, n-1)
		for _, s := range r.shards {
			if s != donor {
				receivers = append(receivers, s)
			}
		}
		sort.Slice(receivers, func(i, j int) bool {
			if working[receivers[i]] != working[receivers[j]] {
				return working[receivers[i]] < working[receivers[j]]
			}
			return receivers[i] < receivers[j]
		})
		for _, recv := range receivers {
			for working[donor] > ceiling && working[recv] < ceiling && len(owned[donor]) > 0 {
				slot := owned[donor][len(owned[donor])-1]
				owned[donor] = owned[donor][:len(owned[donor])-1]
				moves = append(moves, Move{Start: slot, End: slot + 1, From: donor, To: recv})
				working[donor]--
				working[recv]++
			}
			if working[donor] <= ceiling {
				break
			}
		}
	}

	sort.Slice(moves, func(i, j int) bool { return moves[i].Start < moves[j].Start })
	coalesced := []Move{}
	for _, m := range moves {
		if len(coalesced) > 0 {
			last := &coalesced[len(coalesced)-1]
			if m.Start == last.End && m.From == last.From && m.To == last.To {
				last.End = m.End
				continue
			}
		}
		coalesced = append(coalesced, m)
	}
	return coalesced
}
