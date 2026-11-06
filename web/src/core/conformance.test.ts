import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { fnv1a64, hotShards, planRebalance, ShardRouter, slotFor } from "./atlas";

const here = dirname(fileURLToPath(import.meta.url));
const v = JSON.parse(readFileSync(resolve(here, "../../../conformance/vectors.json"), "utf-8"));

describe("conformance", () => {
  it("hash", () => {
    for (const [probe, hex] of Object.entries(v.hash)) {
      expect(fnv1a64(probe)).toBe(BigInt(hex as string));
    }
  });
  it("placement + slots", () => {
    const r = new ShardRouter(v.shards);
    for (const [tenant, shard] of Object.entries(v.placement)) expect(r.shardFor(tenant)).toBe(shard);
    for (const [tenant, slot] of Object.entries(v.slot_for)) expect(slotFor(tenant)).toBe(slot);
  });
  it("hot shards", () => {
    expect(hotShards(v.hot.load, v.hot.overload_pct)).toEqual(v.hot.result);
  });
  it("rebalance plan", () => {
    const r = new ShardRouter(v.shards);
    expect(planRebalance(r, v.rebalance.load, v.rebalance.overload_pct)).toEqual(v.rebalance.plan);
  });
});
