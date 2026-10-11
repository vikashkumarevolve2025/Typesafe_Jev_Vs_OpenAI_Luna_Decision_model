"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import Board from "./Board";
import PlayerCard from "./PlayerCard";
import CallInspector from "./CallInspector";
import { fetchPlayers, requestMove } from "@/lib/api";
import { emptyStats, type Color, type MoveResponse, type PlayerInfo, type PlyRecord, type SideStats } from "@/lib/types";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Threefold repetition and the 50-move rule are only *claimable* draws, so the game
// plays on. Like the backend (python-chess is_game_over), stop only on the automatic
// draws: fivefold repetition and the 75-move rule.
function isFivefoldRepetition(game: Chess): boolean {
  const key = (fen: string) => fen.split(" ").slice(0, 4).join(" ");
  const current = key(game.fen());
  const seen = game.history({ verbose: true }).filter((m) => key(m.before) === current).length;
  return seen + 1 >= 5;
}

function describeResult(game: Chess, maxPlies: number): string {
  if (game.isCheckmate()) return `Checkmate — ${game.turn() === "w" ? "Black" : "White"} wins`;
  if (game.isStalemate()) return "Draw — stalemate";
  if (game.isInsufficientMaterial()) return "Draw — insufficient material";
  if (isFivefoldRepetition(game)) return "Draw — fivefold repetition";
  if (Number(game.fen().split(" ")[4]) >= 150) return "Draw — 75-move rule";
  if (game.history().length >= maxPlies) return `Stopped — reached ${maxPlies} plies`;
  return "";
}

function addToStats(s: SideStats, r: MoveResponse): SideStats {
  // A failed call bills no tokens, so $0 is exact; only real usage without a price is "unknown".
  const billed = r.usage.input_tokens + r.usage.output_tokens + r.usage.cache_read_tokens + r.usage.cache_write_tokens;
  const priced = r.cost_usd !== null || r.player.kind === "offline" || billed === 0;
  return {
    moves: s.moves + 1,
    costUsd: s.costUsd + (r.cost_usd ?? 0),
    costKnown: s.costKnown && priced,
    latencyMsTotal: s.latencyMsTotal + r.latency_ms,
    inputTokens: s.inputTokens + r.usage.input_tokens + r.usage.cache_read_tokens + r.usage.cache_write_tokens,
    outputTokens: s.outputTokens + r.usage.output_tokens,
    cachedTokens: s.cachedTokens + r.usage.cache_read_tokens,
    fallbacks: s.fallbacks + (r.fallback ? 1 : 0),
  };
}

export default function Arena() {
  const [players, setPlayers] = useState<PlayerInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [white, setWhite] = useState("");
  const [black, setBlack] = useState("");

  const gameRef = useRef(new Chess());
  const movesRef = useRef<string[]>([]);
  const runningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const [fen, setFen] = useState(gameRef.current.fen());
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);
  const [plies, setPlies] = useState<PlyRecord[]>([]);
  const [stats, setStats] = useState<Record<Color, SideStats>>({ white: emptyStats(), black: emptyStats() });
  const [running, setRunning] = useState(false);
  const [thinking, setThinking] = useState<Color | null>(null);
  const [status, setStatus] = useState("Pick two players and press Play.");
  const [error, setError] = useState<string | null>(null);
  const [selectedPly, setSelectedPly] = useState<number | null>(null);
  const [follow, setFollow] = useState(true);

  // Settings
  const [compact, setCompact] = useState(true);
  const [maxRetries, setMaxRetries] = useState(1);
  const [delayMs, setDelayMs] = useState(400);
  const [maxPlies, setMaxPlies] = useState(200);

  useEffect(() => {
    fetchPlayers()
      .then((list) => {
        setPlayers(list);
        const pick = (preferred: string[]) =>
          preferred.find((id) => list.some((p) => p.id === id && p.available)) ??
          list.find((p) => p.available)?.id ??
          "";
        setWhite(pick(["claude-opus-5.5", "claude-sonnet-5.5", "greedy"]));
        setBlack(pick(["jev", "greedy", "random"]));
      })
      .catch((e) => setLoadError(`Could not reach the backend: ${e.message}`));
  }, []);

  const playerById = useMemo(() => Object.fromEntries(players.map((p) => [p.id, p])), [players]);

  const reset = useCallback(() => {
    gameRef.current = new Chess();
    movesRef.current = [];
    setFen(gameRef.current.fen());
    setLastMove(null);
    setPlies([]);
    setStats({ white: emptyStats(), black: emptyStats() });
    setSelectedPly(null);
    setError(null);
    setStatus("Pick two players and press Play.");
  }, []);

  const stop = useCallback(() => {
    runningRef.current = false;
    abortRef.current?.abort();
    setRunning(false);
    setThinking(null);
  }, []);

  const play = useCallback(async () => {
    if (!white || !black) return;
    if (gameRef.current.isGameOver() || gameRef.current.history().length >= maxPlies) reset();
    setError(null);
    runningRef.current = true;
    setRunning(true);

    while (runningRef.current) {
      const game = gameRef.current;
      const over = describeResult(game, maxPlies);
      if (over) {
        setStatus(over);
        break;
      }
      const color: Color = game.turn() === "w" ? "white" : "black";
      const playerId = color === "white" ? white : black;
      setThinking(color);
      setStatus(`${playerById[playerId]?.label ?? playerId} (${color}) is thinking…`);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let resp: MoveResponse;
      try {
        resp = await requestMove(
          { player_id: playerId, moves_uci: movesRef.current, compact_prompt: compact, max_retries: maxRetries },
          ctrl.signal,
        );
      } catch (e) {
        if (ctrl.signal.aborted) break;
        setError(e instanceof Error ? e.message : String(e));
        break;
      }
      if (!runningRef.current) break;

      const uci = resp.move_uci;
      let san: string;
      try {
        const mv = game.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
        san = mv.san;
      } catch {
        setError(`Backend returned an illegal move ${uci} — stopping.`);
        break;
      }

      const ply = movesRef.current.length;
      movesRef.current = [...movesRef.current, uci];
      setFen(game.fen());
      setLastMove({ from: uci.slice(0, 2), to: uci.slice(2, 4) });
      setPlies((prev) => [...prev, { ply, color, san, uci, response: resp }]);
      setStats((prev) => ({ ...prev, [color]: addToStats(prev[color], resp) }));
      setThinking(null);
      if (follow) setSelectedPly(ply);

      await sleep(delayMs);
    }

    runningRef.current = false;
    setRunning(false);
    setThinking(null);
    const final = describeResult(gameRef.current, maxPlies);
    if (final) setStatus(final);
    else setStatus((s) => (s.endsWith("thinking…") ? "Paused." : s));
  }, [white, black, maxPlies, reset, compact, maxRetries, delayMs, follow, playerById]);

  const swapSides = () => {
    setWhite(black);
    setBlack(white);
  };

  const copyPgn = async () => {
    const g = gameRef.current;
    g.setHeader("White", playerById[white]?.label ?? white);
    g.setHeader("Black", playerById[black]?.label ?? black);
    await navigator.clipboard.writeText(g.pgn());
    setStatus("PGN copied to clipboard.");
  };

  const selected = plies.find((p) => p.ply === selectedPly) ?? null;
  const pliesFor = (c: Color) => plies.filter((p) => p.color === c);
  const label = (id: string) => playerById[id]?.label ?? id;

  return (
    <main className="arena">
      <h1>LLM Chess Arena</h1>
      {loadError && <div className="banner error">{loadError} — is the FastAPI server running on :8000?</div>}

      <div className="layout">
        <div className="left">
          <div className="board-label">
            <b>{label(black)}</b> <span className="muted small">black</span>
            {thinking === "black" && <span className="dot" />}
          </div>
          <Board fen={fen} lastMove={lastMove} />
          <div className="board-label">
            <b>{label(white)}</b> <span className="muted small">white</span>
            {thinking === "white" && <span className="dot" />}
          </div>
          <p className="status">{status}</p>
          {error && <div className="banner error">{error}</div>}
          <CallInspector key={selected?.ply ?? -1} record={selected} />
        </div>

        <div className="right">
          <div className="controls">
            <button className="btn primary" onClick={play} disabled={running || !white || !black}>
              Play
            </button>
            <button className="btn" onClick={stop} disabled={!running}>
              Stop
            </button>
            <button className="btn" onClick={reset} disabled={running}>
              Reset
            </button>
            <button className="btn" onClick={swapSides} disabled={running}>
              Swap sides
            </button>
            <button className="btn" onClick={copyPgn} disabled={plies.length === 0}>
              Copy PGN
            </button>
          </div>

          <div className="settings card">
            <label title="Compact: FEN + material + numbered SAN list. Verbose: every piece, square and move description.">
              <input type="checkbox" checked={compact} onChange={(e) => setCompact(e.target.checked)} disabled={running} />
              Compact prompt
            </label>
            <label>
              Retries on invalid reply
              <select value={maxRetries} onChange={(e) => setMaxRetries(Number(e.target.value))} disabled={running}>
                {[0, 1, 2].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Delay
              <select value={delayMs} onChange={(e) => setDelayMs(Number(e.target.value))}>
                {[0, 200, 400, 800, 1500].map((n) => (
                  <option key={n} value={n}>
                    {n} ms
                  </option>
                ))}
              </select>
            </label>
            <label>
              Max plies
              <select value={maxPlies} onChange={(e) => setMaxPlies(Number(e.target.value))} disabled={running}>
                {[40, 100, 200, 400].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
                <option value={Infinity}>No limit</option>
              </select>
            </label>
            <label>
              <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
              Inspector follows latest move
            </label>
          </div>

          <PlayerCard
            index={1}
            color="white"
            players={players}
            value={white}
            onChange={setWhite}
            disabled={running}
            stats={stats.white}
            plies={pliesFor("white")}
            thinking={thinking === "white"}
            onSelectPly={setSelectedPly}
            selectedPly={selectedPly}
          />
          <PlayerCard
            index={2}
            color="black"
            players={players}
            value={black}
            onChange={setBlack}
            disabled={running}
            stats={stats.black}
            plies={pliesFor("black")}
            thinking={thinking === "black"}
            onSelectPly={setSelectedPly}
            selectedPly={selectedPly}
          />
        </div>
      </div>
    </main>
  );
}
