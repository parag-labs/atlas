package atlas

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"testing"
)

type vectors struct {
	Hash      map[string]string `json:"hash"`
	Shards    []string          `json:"shards"`
	Placement map[string]string `json:"placement"`
	SlotFor   map[string]int    `json:"slot_for"`
	Hot       struct {
		Load        map[string]int `json:"load"`
		OverloadPct int            `json:"overload_pct"`
		Result      []string       `json:"result"`
	} `json:"hot"`
	Rebalance struct {
		Load        map[string]int `json:"load"`
		OverloadPct int            `json:"overload_pct"`
		Plan        []Move         `json:"plan"`
	} `json:"rebalance"`
}

func load(t *testing.T) vectors {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("..", "conformance", "vectors.json"))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	var v vectors
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatalf("parse: %v", err)
	}
	return v
}

func TestConformanceHash(t *testing.T) {
	for probe, hex := range load(t).Hash {
		want, _ := strconv.ParseUint(hex[2:], 16, 64)
		if got := Fnv1a64(probe); got != want {
			t.Errorf("fnv(%q)=%#x want %s", probe, got, hex)
		}
	}
}

func TestConformancePlacement(t *testing.T) {
	v := load(t)
	r := NewShardRouter(v.Shards)
	for tenant, shard := range v.Placement {
		if got := r.ShardFor(tenant); got != shard {
			t.Errorf("placement[%s]=%s want %s", tenant, got, shard)
		}
	}
	for tenant, slot := range v.SlotFor {
		if got := SlotFor(tenant); got != slot {
			t.Errorf("slot[%s]=%d want %d", tenant, got, slot)
		}
	}
}

func TestConformanceHot(t *testing.T) {
	v := load(t)
	got := HotShards(v.Hot.Load, v.Hot.OverloadPct)
	if len(got) != len(v.Hot.Result) {
		t.Fatalf("hot=%v want %v", got, v.Hot.Result)
	}
	for i := range got {
		if got[i] != v.Hot.Result[i] {
			t.Errorf("hot[%d]=%s want %s", i, got[i], v.Hot.Result[i])
		}
	}
}

func TestConformanceRebalance(t *testing.T) {
	v := load(t)
	r := NewShardRouter(v.Shards)
	got := PlanRebalance(r, v.Rebalance.Load, v.Rebalance.OverloadPct)
	if len(got) != len(v.Rebalance.Plan) {
		t.Fatalf("plan has %d moves, want %d", len(got), len(v.Rebalance.Plan))
	}
	for i, m := range got {
		w := v.Rebalance.Plan[i]
		if m != w {
			t.Errorf("move[%d]=%+v want %+v", i, m, w)
		}
	}
}
