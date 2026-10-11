"use client";

import { useState } from "react";
import type { PlyRecord } from "@/lib/types";
import { int, ms, pretty, usd } from "@/lib/format";

type Tab = "data" | "prompts" | "reply";

type Props = {
  record: PlyRecord | null;
};

function Pre({ value }: { value: unknown }) {
  return <pre className="code">{pretty(value)}</pre>;
}

export default function CallInspector({ record }: Props) {
  const [tab, setTab] = useState<Tab>("data");
  const [attemptIdx, setAttemptIdx] = useState(0);

  const r = record?.response;
  const calls = r?.calls ?? [];
  const call = calls[Math.min(attemptIdx, Math.max(calls.length - 1, 0))];

  return (
    <section className="card inspector">
      <div className="tabs">
        {(
          [
            ["data", "Data sent"],
            ["prompts", "Prompts"],
            ["reply", "Reply & usage"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} className={tab === key ? "tab active" : "tab"} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
        {record && (
          <span className="tab-meta muted small">
            Ply {record.ply + 1} · {record.color} · {r!.player.label} · <b>{record.san}</b>
            {r!.fallback && <span className="warn"> · fallback</span>}
          </span>
        )}
      </div>

      {!record && (
        <p className="muted pad">The exact payload, prompts and reply for each move show up here.</p>
      )}

      {record && r && (
        <div className="pad">
          {calls.length > 1 && (
            <div className="attempts">
              Attempts:
              {calls.map((c, i) => (
                <button
                  key={i}
                  className={i === attemptIdx ? "chip active" : "chip"}
                  onClick={() => setAttemptIdx(i)}
                >
                  #{c.attempt}
                  {c.parsed_move ? "" : " ✗"}
                </button>
              ))}
            </div>
          )}

          {tab === "data" && (
            <>
              <h4>Structured state ({r.prompt_mode} prompt)</h4>
              <div className="state-summary">
                <span>
                  Side to move: <b>{r.encoded.side_to_move}</b>
                </span>
                <span>
                  Material: W {r.encoded.material.white} · B {r.encoded.material.black} (balance{" "}
                  {r.encoded.material.balance >= 0 ? "+" : ""}
                  {r.encoded.material.balance})
                </span>
                <span>
                  Legal moves: <b>{r.encoded.legal_moves.length}</b>
                </span>
                {r.encoded.in_check && <span className="warn">In check</span>}
              </div>
              <h4>Numbered choices</h4>
              <div className="choices">
                {r.encoded.legal_moves.map((m) => (
                  <span key={m.n} className={m.uci === r.move_uci ? "choice picked" : "choice"}>
                    {m.n}. {m.san}
                  </span>
                ))}
              </div>
              <h4>Exact request payload</h4>
              {call ? <Pre value={call.request} /> : <p className="muted">Offline player — no request sent.</p>}
            </>
          )}

          {tab === "prompts" && (call ? <Pre value={call.prompts} /> : <p className="muted">No prompt.</p>)}

          {tab === "reply" && call && (
            <>
              <div className="state-summary">
                <span>
                  Latency <b>{ms(call.latency_ms)}</b>
                </span>
                <span>
                  Cost <b>{usd(call.cost_usd, 6)}</b>
                </span>
                <span>
                  In <b>{int(call.usage.input_tokens)}</b> · Out <b>{int(call.usage.output_tokens)}</b>
                </span>
                <span>
                  Cache read <b>{int(call.usage.cache_read_tokens)}</b> · write{" "}
                  <b>{int(call.usage.cache_write_tokens)}</b>
                </span>
                <span>
                  Stop reason <b>{call.stop_reason ?? "—"}</b>
                </span>
                <span>
                  Parsed move <b>{call.parsed_move ?? "none"}</b>
                </span>
              </div>
              {call.diagnosis && <div className="diagnosis">🔎 {call.diagnosis}</div>}
              {call.error && <div className="diagnosis error">Error: {call.error}</div>}
              {r.fallback && (
                <div className="diagnosis">
                  Fallback played <b>{r.move_san}</b>: {r.fallback_reason}
                </div>
              )}
              {call.signals && (
                <>
                  <h4>Decision signals</h4>
                  <Pre value={call.signals} />
                </>
              )}
              <h4>Raw reply</h4>
              <Pre value={call.reply} />
            </>
          )}
          {tab === "reply" && !call && (
            <p className="muted">
              Offline player chose <b>{r.move_san}</b> locally ({ms(r.latency_ms)}).
            </p>
          )}
        </div>
      )}
    </section>
  );
}
