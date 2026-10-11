"use client";

import type { Color, PlayerInfo, PlyRecord, SideStats } from "@/lib/types";
import { int, ms, usd } from "@/lib/format";

type Props = {
  index: 1 | 2;
  color: Color;
  players: PlayerInfo[];
  value: string;
  onChange: (id: string) => void;
  disabled: boolean;
  stats: SideStats;
  plies: PlyRecord[];
  thinking: boolean;
  onSelectPly: (ply: number) => void;
  selectedPly: number | null;
};

function groupPlayers(players: PlayerInfo[]) {
  const groups = new Map<string, PlayerInfo[]>();
  for (const p of players) {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group)!.push(p);
  }
  return [...groups.entries()];
}

export default function PlayerCard(props: Props) {
  const { index, color, players, value, onChange, disabled, stats, plies, thinking } = props;
  const perMove = stats.moves ? stats.costUsd / stats.moves : 0;
  const avgLatency = stats.moves ? stats.latencyMsTotal / stats.moves : 0;
  const costLabel = (v: number) => (stats.costKnown ? usd(v) : `${usd(v)}*`);

  return (
    <section className="card">
      <div className="card-head">
        <span className="muted small">
          Player {index} · {color}
        </span>
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
          {groupPlayers(players).map(([group, list]) => (
            <optgroup key={group} label={group}>
              {list.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.available}>
                  {p.label}
                  {p.note ? ` (${p.note})` : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      <div className="metrics">
        <span>
          Game cost <b>{costLabel(stats.costUsd)}</b>
        </span>
        <span>
          Per move <b>{costLabel(perMove)}</b>
        </span>
        <span>
          Avg latency <b>{ms(avgLatency)}</b>
        </span>
        <span>
          Tokens <b>{int(stats.inputTokens + stats.outputTokens)}</b> (cached {int(stats.cachedTokens)})
        </span>
        {stats.fallbacks > 0 && (
          <span className="warn">
            Fallbacks <b>{stats.fallbacks}</b>
          </span>
        )}
      </div>

      <div className="moves">
        {plies.length === 0 && !thinking && <span className="muted">No moves yet</span>}
        {plies.map((p) => (
          <button
            key={p.ply}
            className={`move-chip ${p.response.fallback ? "fallback" : ""} ${
              props.selectedPly === p.ply ? "selected" : ""
            }`}
            title={
              p.response.fallback
                ? `Fallback move: ${p.response.fallback_reason}`
                : `${ms(p.response.latency_ms)} · ${usd(p.response.cost_usd)}`
            }
            onClick={() => props.onSelectPly(p.ply)}
          >
            {Math.floor(p.ply / 2) + 1}
            {color === "white" ? "." : "…"} {p.san}
            {p.response.fallback ? " ⚠" : ""}
          </button>
        ))}
        {thinking && <span className="thinking">thinking…</span>}
      </div>
      {!stats.costKnown && (
        <div className="muted small footnote">* price unknown for this model — set it in backend/.env</div>
      )}
    </section>
  );
}
