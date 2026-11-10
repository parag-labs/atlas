import { useMemo, useState } from "react";
import { hotShards, type Move, planRebalance, ShardRouter, SLOTS } from "./core/atlas";

const SHARDS = ["shard-0", "shard-1", "shard-2", "shard-3", "shard-4"];
const COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899"];
const OVERLOAD_PCT = 20;

export function App() {
  const [load, setLoad] = useState<number[]>([800, 150, 130, 160, 140]);

  const router = useMemo(() => new ShardRouter(SHARDS), []);
  const loadMap = useMemo(
    () => Object.fromEntries(SHARDS.map((s, i) => [s, load[i]])),
    [load],
  );
  const hot = useMemo(() => hotShards(loadMap, OVERLOAD_PCT), [loadMap]);
  const plan = useMemo(() => planRebalance(router, loadMap, OVERLOAD_PCT), [router, loadMap]);

  const color = (shard: string) => COLORS[SHARDS.indexOf(shard) % COLORS.length];
  const total = load.reduce((a, b) => a + b, 0);
  const mean = total / SHARDS.length;

  // Slot ownership arcs for the ring: each shard owns a contiguous range.
  const arcs = useMemo(() => {
    const out: { shard: string; from: number; to: number }[] = [];
    let cur = router.slotOwner(0);
    let start = 0;
    for (let s = 1; s < SLOTS; s++) {
      const owner = router.slotOwner(s);
      if (owner !== cur) {
        out.push({ shard: cur, from: start, to: s });
        cur = owner;
        start = s;
      }
    }
    out.push({ shard: cur, from: start, to: SLOTS });
    return out;
  }, [router]);

  const R = 150;
  const cx = 175;
  const cy = 175;
  const polar = (slot: number) => {
    const a = (slot / SLOTS) * Math.PI * 2 - Math.PI / 2;
    return [cx + Math.cos(a) * R, cy + Math.sin(a) * R];
  };
  const arcPath = (from: number, to: number) => {
    const [x1, y1] = polar(from);
    const [x2, y2] = polar(to);
    const large = to - from > SLOTS / 2 ? 1 : 0;
    return `M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2}`;
  };

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="dot" /> Atlas</div>
        <h1>Multi-tenant shard map & rebalance</h1>
        <p className="lede">
          {SLOTS.toLocaleString()} hash slots split evenly across {SHARDS.length} shards.
          Tenants hash into a slot; each shard owns a contiguous arc. Push one shard's
          load up and Atlas flags it hot and computes the exact slot ranges to move.
        </p>
      </header>

      <div className="stage">
        <svg viewBox="0 0 350 350" className="ring">
          {arcs.map((a, i) => (
            <path
              key={i}
              d={arcPath(a.from, a.to)}
              stroke={color(a.shard)}
              strokeWidth={hot.includes(a.shard) ? 20 : 12}
              fill="none"
              opacity={hot.includes(a.shard) ? 1 : 0.85}
            />
          ))}
          {/* rebalance moves drawn as a highlight ring just inside */}
          {plan.map((m, i) => {
            const [x1, y1] = polar(m.start);
            const [x2, y2] = polar(m.end);
            const large = m.end - m.start > SLOTS / 2 ? 1 : 0;
            return (
              <path
                key={`m${i}`}
                d={`M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2}`}
                stroke={color(m.to)}
                strokeWidth={6}
                strokeDasharray="4 3"
                fill="none"
                transform={`translate(${(cx - x1) * 0}, 0)`}
              />
            );
          })}
          <text x={cx} y={cy - 4} className="ring-c">{SHARDS.length}</text>
          <text x={cx} y={cy + 16} className="ring-s">shards</text>
        </svg>

        <div className="panel">
          <div className="shards">
            {SHARDS.map((s, i) => {
              const isHot = hot.includes(s);
              return (
                <div className={isHot ? "shard hot" : "shard"} key={s}>
                  <div className="s-top">
                    <span className="s-dot" style={{ background: color(s) }} />
                    <span className="s-name">{s}</span>
                    {isHot && <span className="hot-tag">HOT</span>}
                    <span className="s-load">{load[i]}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={1000}
                    value={load[i]}
                    onChange={(e) => {
                      const next = [...load];
                      next[i] = +e.target.value;
                      setLoad(next);
                    }}
                  />
                  <div className="s-bar">
                    <div className="s-fill" style={{ width: `${(load[i] / Math.max(...load)) * 100}%`, background: color(s) }} />
                    <div className="s-mean" style={{ left: `${(mean / Math.max(...load)) * 100}%` }} title="mean" />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="plan">
            <div className="plan-head">
              Rebalance plan <span className="muted">(threshold +{OVERLOAD_PCT}% over mean)</span>
            </div>
            {plan.length === 0 ? (
              <div className="plan-empty">Balanced — no shard is hot, nothing to move.</div>
            ) : (
              <ul>
                {plan.map((m: Move, i) => (
                  <li key={i}>
                    move slots <b>{m.start.toLocaleString()}–{m.end.toLocaleString()}</b>{" "}
                    <span style={{ color: color(m.from) }}>{m.from}</span> →{" "}
                    <span style={{ color: color(m.to) }}>{m.to}</span>{" "}
                    <span className="muted">({(m.end - m.start).toLocaleString()} slots)</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <footer>
        <span>Same core in Python · Go · Rust · C# · Java · TypeScript — placement and the plan are identical across all six.</span>
        <a href="https://github.com/parag-labs/atlas">Source →</a>
      </footer>
    </div>
  );
}
