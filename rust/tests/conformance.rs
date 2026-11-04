use atlas::{fnv1a_64, hot_shards, plan_rebalance, slot_for, Move, ShardRouter};
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

fn vectors() -> Value {
    let p = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("conformance")
        .join("vectors.json");
    serde_json::from_str(&fs::read_to_string(p).unwrap()).unwrap()
}

fn load_map(v: &Value) -> HashMap<String, i64> {
    v.as_object()
        .unwrap()
        .iter()
        .map(|(k, val)| (k.clone(), val.as_i64().unwrap()))
        .collect()
}

fn strs(v: &Value) -> Vec<&str> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_str().unwrap())
        .collect()
}

#[test]
fn conformance_hash() {
    let v = vectors();
    for (probe, hex) in v["hash"].as_object().unwrap() {
        let want = u64::from_str_radix(hex.as_str().unwrap().trim_start_matches("0x"), 16).unwrap();
        assert_eq!(fnv1a_64(probe), want, "{probe}");
    }
}

#[test]
fn conformance_placement() {
    let v = vectors();
    let r = ShardRouter::new(&strs(&v["shards"]));
    for (tenant, shard) in v["placement"].as_object().unwrap() {
        assert_eq!(r.shard_for(tenant), shard.as_str().unwrap(), "{tenant}");
    }
    for (tenant, slot) in v["slot_for"].as_object().unwrap() {
        assert_eq!(slot_for(tenant) as i64, slot.as_i64().unwrap(), "{tenant}");
    }
}

#[test]
fn conformance_hot() {
    let v = vectors();
    let load = load_map(&v["hot"]["load"]);
    let got = hot_shards(&load, v["hot"]["overload_pct"].as_i64().unwrap());
    let want: Vec<&str> = strs(&v["hot"]["result"]);
    assert_eq!(got, want);
}

#[test]
fn conformance_rebalance() {
    let v = vectors();
    let r = ShardRouter::new(&strs(&v["shards"]));
    let load = load_map(&v["rebalance"]["load"]);
    let got = plan_rebalance(&r, &load, v["rebalance"]["overload_pct"].as_i64().unwrap());
    let want: Vec<Move> = v["rebalance"]["plan"]
        .as_array()
        .unwrap()
        .iter()
        .map(|m| Move {
            start: m["start"].as_u64().unwrap() as usize,
            end: m["end"].as_u64().unwrap() as usize,
            from: m["from"].as_str().unwrap().to_string(),
            to: m["to"].as_str().unwrap().to_string(),
        })
        .collect();
    assert_eq!(got, want);
}
