namespace Atlas;

/// <summary>
/// Atlas: multi-tenant shard placement, hot-shard detection, and rebalance planning
/// over a fixed hash-slot space. Integer arithmetic only, so every language port agrees
/// byte-for-byte (see conformance/).
/// </summary>
public static class Hashing
{
    public const int Slots = 16384;
    private const ulong Fnv64Offset = 0xCBF29CE484222325;
    private const ulong Fnv64Prime = 0x100000001B3;

    public static ulong Fnv1a64(string s)
    {
        ulong h = Fnv64Offset;
        foreach (var b in System.Text.Encoding.UTF8.GetBytes(s))
        {
            h ^= b;
            h *= Fnv64Prime;
        }
        return h;
    }

    public static int SlotFor(string tenant) => (int)(Fnv1a64(tenant) % Slots);
}

public readonly record struct Move(int Start, int End, string From, string To);

public sealed class ShardRouter
{
    private readonly string[] _shards;
    private readonly int[] _owner;

    public ShardRouter(IReadOnlyList<string> shards)
    {
        if (shards.Count == 0) throw new ArgumentException("need at least one shard");
        _shards = shards.ToArray();
        var n = _shards.Length;
        _owner = new int[Hashing.Slots];
        var baseSize = Hashing.Slots / n;
        var rem = Hashing.Slots % n;
        var slot = 0;
        for (var shardIdx = 0; shardIdx < n; shardIdx++)
        {
            var size = baseSize + (shardIdx < rem ? 1 : 0);
            for (var i = 0; i < size; i++) _owner[slot++] = shardIdx;
        }
    }

    public string ShardFor(string tenant) => _shards[_owner[Hashing.SlotFor(tenant)]];
    public string SlotOwner(int slot) => _shards[_owner[slot]];
    public IReadOnlyList<string> Shards => _shards;
}

public static class Balancer
{
    public static List<string> HotShards(IReadOnlyDictionary<string, int> load, int overloadPct)
    {
        if (load.Count == 0) return new List<string>();
        var n = load.Count;
        var total = load.Values.Sum();
        long thresholdNum = (long)total * (100 + overloadPct);
        return load.Where(kv => (long)kv.Value * 100 * n > thresholdNum)
            .Select(kv => kv.Key)
            .OrderByDescending(s => load[s])
            .ThenBy(s => s, StringComparer.Ordinal)
            .ToList();
    }

    public static List<Move> PlanRebalance(
        ShardRouter router, IReadOnlyDictionary<string, int> load, int overloadPct)
    {
        var hot = HotShards(load, overloadPct);
        if (hot.Count == 0) return new List<Move>();

        var working = new Dictionary<string, int>(load);
        var n = router.Shards.Count;
        var total = load.Values.Sum();
        var ceiling = (int)((long)total * (100 + overloadPct) / (100 * n));

        var owned = router.Shards.ToDictionary(s => s, _ => new List<int>());
        for (var slot = 0; slot < Hashing.Slots; slot++)
            owned[router.SlotOwner(slot)].Add(slot);

        var moves = new List<Move>();
        foreach (var donor in hot)
        {
            var receivers = router.Shards.Where(s => s != donor)
                .OrderBy(s => working[s]).ThenBy(s => s, StringComparer.Ordinal).ToList();
            foreach (var recv in receivers)
            {
                while (working[donor] > ceiling && working[recv] < ceiling && owned[donor].Count > 0)
                {
                    var slot = owned[donor][^1];
                    owned[donor].RemoveAt(owned[donor].Count - 1);
                    moves.Add(new Move(slot, slot + 1, donor, recv));
                    working[donor]--;
                    working[recv]++;
                }
                if (working[donor] <= ceiling) break;
            }
        }

        moves.Sort((a, b) => a.Start.CompareTo(b.Start));
        var coalesced = new List<Move>();
        foreach (var m in moves)
        {
            if (coalesced.Count > 0)
            {
                var last = coalesced[^1];
                if (m.Start == last.End && m.From == last.From && m.To == last.To)
                {
                    coalesced[^1] = last with { End = m.End };
                    continue;
                }
            }
            coalesced.Add(m);
        }
        return coalesced;
    }
}
