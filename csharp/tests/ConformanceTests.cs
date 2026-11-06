using System.Text.Json;
using Xunit;

namespace Atlas.Tests;

public class ConformanceTests
{
    private static readonly JsonElement V = Load();

    private static JsonElement Load()
    {
        var dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "conformance", "vectors.json")))
            dir = Directory.GetParent(dir)?.FullName;
        if (dir is null) throw new FileNotFoundException("conformance/vectors.json");
        return JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "conformance", "vectors.json")))
            .RootElement.Clone();
    }

    private static string[] Strs(JsonElement e) =>
        e.EnumerateArray().Select(x => x.GetString()!).ToArray();

    private static Dictionary<string, int> LoadMap(JsonElement e) =>
        e.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetInt32());

    [Fact]
    public void HashMatches()
    {
        foreach (var p in V.GetProperty("hash").EnumerateObject())
        {
            var want = Convert.ToUInt64(p.Value.GetString()![2..], 16);
            Assert.Equal(want, Hashing.Fnv1a64(p.Name));
        }
    }

    [Fact]
    public void PlacementMatches()
    {
        var r = new ShardRouter(Strs(V.GetProperty("shards")));
        foreach (var p in V.GetProperty("placement").EnumerateObject())
            Assert.Equal(p.Value.GetString(), r.ShardFor(p.Name));
        foreach (var p in V.GetProperty("slot_for").EnumerateObject())
            Assert.Equal(p.Value.GetInt32(), Hashing.SlotFor(p.Name));
    }

    [Fact]
    public void HotMatches()
    {
        var hot = V.GetProperty("hot");
        var got = Balancer.HotShards(LoadMap(hot.GetProperty("load")), hot.GetProperty("overload_pct").GetInt32());
        Assert.Equal(Strs(hot.GetProperty("result")), got.ToArray());
    }

    [Fact]
    public void RebalanceMatches()
    {
        var reb = V.GetProperty("rebalance");
        var r = new ShardRouter(Strs(V.GetProperty("shards")));
        var got = Balancer.PlanRebalance(r, LoadMap(reb.GetProperty("load")), reb.GetProperty("overload_pct").GetInt32());
        var want = reb.GetProperty("plan").EnumerateArray().Select(m => new Move(
            m.GetProperty("start").GetInt32(), m.GetProperty("end").GetInt32(),
            m.GetProperty("from").GetString()!, m.GetProperty("to").GetString()!)).ToList();
        Assert.Equal(want, got);
    }
}
