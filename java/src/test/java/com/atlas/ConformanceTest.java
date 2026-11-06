package com.atlas;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.atlas.Atlas.Move;
import com.atlas.Atlas.ShardRouter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.Test;

class ConformanceTest {

    private static JSONObject vectors() throws IOException {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("conformance/vectors.json"))) {
            dir = dir.getParent();
        }
        if (dir == null) throw new IOException("conformance/vectors.json not found");
        return new JSONObject(Files.readString(dir.resolve("conformance/vectors.json")));
    }

    private static List<String> strs(JSONArray a) {
        List<String> out = new ArrayList<>();
        for (int i = 0; i < a.length(); i++) out.add(a.getString(i));
        return out;
    }

    private static Map<String, Integer> loadMap(JSONObject o) {
        Map<String, Integer> m = new HashMap<>();
        for (String k : o.keySet()) m.put(k, o.getInt(k));
        return m;
    }

    @Test
    void hashMatches() throws IOException {
        JSONObject h = vectors().getJSONObject("hash");
        for (String probe : h.keySet()) {
            assertEquals(Long.parseUnsignedLong(h.getString(probe).substring(2), 16), Atlas.fnv1a64(probe));
        }
    }

    @Test
    void placementMatches() throws IOException {
        JSONObject v = vectors();
        ShardRouter r = new ShardRouter(strs(v.getJSONArray("shards")));
        JSONObject placement = v.getJSONObject("placement");
        for (String tenant : placement.keySet()) {
            assertEquals(placement.getString(tenant), r.shardFor(tenant));
        }
        JSONObject slots = v.getJSONObject("slot_for");
        for (String tenant : slots.keySet()) {
            assertEquals(slots.getInt(tenant), Atlas.slotFor(tenant));
        }
    }

    @Test
    void hotMatches() throws IOException {
        JSONObject hot = vectors().getJSONObject("hot");
        List<String> got = Atlas.hotShards(loadMap(hot.getJSONObject("load")), hot.getInt("overload_pct"));
        assertEquals(strs(hot.getJSONArray("result")), got);
    }

    @Test
    void rebalanceMatches() throws IOException {
        JSONObject v = vectors();
        JSONObject reb = v.getJSONObject("rebalance");
        ShardRouter r = new ShardRouter(strs(v.getJSONArray("shards")));
        List<Move> got = Atlas.planRebalance(r, loadMap(reb.getJSONObject("load")), reb.getInt("overload_pct"));
        JSONArray plan = reb.getJSONArray("plan");
        List<Move> want = new ArrayList<>();
        for (int i = 0; i < plan.length(); i++) {
            JSONObject m = plan.getJSONObject(i);
            want.add(new Move(m.getInt("start"), m.getInt("end"), m.getString("from"), m.getString("to")));
        }
        assertEquals(want, got);
    }
}
