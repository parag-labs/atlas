package com.atlas;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Atlas: multi-tenant shard placement, hot-shard detection, and rebalance planning over
 * a fixed hash-slot space. Integer arithmetic only, so every language port agrees
 * byte-for-byte (see conformance/).
 */
public final class Atlas {

    public static final int SLOTS = 16384;
    private static final long FNV64_OFFSET = 0xCBF29CE484222325L;
    private static final long FNV64_PRIME = 0x100000001B3L;

    private Atlas() {
    }

    public static long fnv1a64(String s) {
        long h = FNV64_OFFSET;
        for (byte b : s.getBytes(StandardCharsets.UTF_8)) {
            h ^= (b & 0xFF);
            h *= FNV64_PRIME;
        }
        return h;
    }

    public static int slotFor(String tenant) {
        return (int) Long.remainderUnsigned(fnv1a64(tenant), SLOTS);
    }

    public record Move(int start, int end, String from, String to) {
    }

    public static final class ShardRouter {
        private final List<String> shards;
        private final int[] owner;

        public ShardRouter(List<String> shards) {
            if (shards.isEmpty()) throw new IllegalArgumentException("need at least one shard");
            this.shards = new ArrayList<>(shards);
            int n = shards.size();
            this.owner = new int[SLOTS];
            int base = SLOTS / n;
            int rem = SLOTS % n;
            int slot = 0;
            for (int shardIdx = 0; shardIdx < n; shardIdx++) {
                int size = base + (shardIdx < rem ? 1 : 0);
                for (int i = 0; i < size; i++) owner[slot++] = shardIdx;
            }
        }

        public String shardFor(String tenant) {
            return shards.get(owner[slotFor(tenant)]);
        }

        public String slotOwner(int slot) {
            return shards.get(owner[slot]);
        }

        public List<String> shards() {
            return shards;
        }
    }

    public static List<String> hotShards(Map<String, Integer> load, int overloadPct) {
        List<String> hot = new ArrayList<>();
        if (load.isEmpty()) return hot;
        int n = load.size();
        long total = load.values().stream().mapToLong(Integer::longValue).sum();
        long thresholdNum = total * (100 + overloadPct);
        for (Map.Entry<String, Integer> e : load.entrySet()) {
            if ((long) e.getValue() * 100 * n > thresholdNum) hot.add(e.getKey());
        }
        hot.sort(Comparator.<String>comparingInt(s -> -load.get(s)).thenComparing(Comparator.naturalOrder()));
        return hot;
    }

    public static List<Move> planRebalance(ShardRouter router, Map<String, Integer> load, int overloadPct) {
        List<String> hot = hotShards(load, overloadPct);
        if (hot.isEmpty()) return new ArrayList<>();

        Map<String, Integer> working = new HashMap<>(load);
        int n = router.shards().size();
        long total = load.values().stream().mapToLong(Integer::longValue).sum();
        int ceiling = (int) (total * (100 + overloadPct) / (100L * n));

        Map<String, List<Integer>> owned = new HashMap<>();
        for (String s : router.shards()) owned.put(s, new ArrayList<>());
        for (int slot = 0; slot < SLOTS; slot++) owned.get(router.slotOwner(slot)).add(slot);

        List<Move> moves = new ArrayList<>();
        for (String donor : hot) {
            List<String> receivers = new ArrayList<>();
            for (String s : router.shards()) if (!s.equals(donor)) receivers.add(s);
            receivers.sort(Comparator.<String>comparingInt(working::get).thenComparing(Comparator.naturalOrder()));
            for (String recv : receivers) {
                List<Integer> donorSlots = owned.get(donor);
                while (working.get(donor) > ceiling && working.get(recv) < ceiling && !donorSlots.isEmpty()) {
                    int slot = donorSlots.remove(donorSlots.size() - 1);
                    moves.add(new Move(slot, slot + 1, donor, recv));
                    working.put(donor, working.get(donor) - 1);
                    working.put(recv, working.get(recv) + 1);
                }
                if (working.get(donor) <= ceiling) break;
            }
        }

        moves.sort(Comparator.comparingInt(Move::start));
        List<Move> coalesced = new ArrayList<>();
        for (Move m : moves) {
            if (!coalesced.isEmpty()) {
                Move last = coalesced.get(coalesced.size() - 1);
                if (m.start() == last.end() && m.from().equals(last.from()) && m.to().equals(last.to())) {
                    coalesced.set(coalesced.size() - 1, new Move(last.start(), m.end(), last.from(), last.to()));
                    continue;
                }
            }
            coalesced.add(m);
        }
        return coalesced;
    }
}
