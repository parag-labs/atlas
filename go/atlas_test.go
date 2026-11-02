package atlas

import "testing"

func TestEvenSlotDistribution(t *testing.T) {
	r := NewShardRouter([]string{"a", "b", "c", "d", "e"})
	counts := map[string]int{}
	for s := 0; s < Slots; s++ {
		counts[r.SlotOwner(s)]++
	}
	min, max := Slots, 0
	sum := 0
	for _, c := range counts {
		sum += c
		if c < min {
			min = c
		}
		if c > max {
			max = c
		}
	}
	if max-min > 1 {
		t.Fatalf("uneven slot split: %d..%d", min, max)
	}
	if sum != Slots {
		t.Fatalf("slots sum %d != %d", sum, Slots)
	}
}

func TestHotDetection(t *testing.T) {
	got := HotShards(map[string]int{"a": 100, "b": 100, "c": 400}, 25)
	if len(got) != 1 || got[0] != "c" {
		t.Fatalf("want [c], got %v", got)
	}
}

func TestRebalanceTakesFromHotShard(t *testing.T) {
	r := NewShardRouter([]string{"a", "b", "c"})
	moves := PlanRebalance(r, map[string]int{"a": 900, "b": 50, "c": 50}, 20)
	if len(moves) == 0 {
		t.Fatal("expected moves")
	}
	for _, m := range moves {
		if m.From != "a" {
			t.Fatalf("move should come from hot shard a, got %s", m.From)
		}
	}
}
