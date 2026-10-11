// Shapes shared with the FastAPI backend (see backend/app/schemas.py).

export type PlayerInfo = {
  id: string;
  label: string;
  group: string;
  kind: "llm" | "system_one" | "offline";
  available: boolean;
  note?: string | null; // e.g. "missing AWS credentials", "price unknown"
};

export type Usage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
};

export type LegalMoveChoice = {
  n: number;
  uci: string;
  san: string;
  piece: string;
  from: string;
  to: string;
  capture: string | null;
  check: boolean;
  mate: boolean;
  promotion: string | null;
};

export type EncodedState = {
  fen: string;
  side_to_move: "white" | "black";
  move_number: number;
  in_check: boolean;
  pieces: { square: string; piece: string; color: "white" | "black" }[];
  legal_moves: LegalMoveChoice[];
  material: { white: number; black: number; balance: number };
  history_san: string[];
};

export type CallRecord = {
  attempt: number;
  request: unknown; // exact payload sent to the provider
  prompts: Record<string, unknown>; // system/user text, or Jev questions
  reply: unknown; // raw provider reply (reasoning redacted)
  parsed_move: string | null;
  stop_reason: string | null;
  usage: Usage;
  latency_ms: number;
  cost_usd: number | null;
  signals: Record<string, unknown> | null; // Jev score/noul answers, choice probs
  error: string | null;
  diagnosis: string | null; // e.g. "hidden thinking consumed max_tokens"
};

export type MoveResponse = {
  player: PlayerInfo;
  move_uci: string;
  move_san: string;
  fallback: boolean;
  fallback_reason: string | null;
  latency_ms: number;
  cost_usd: number | null;
  usage: Usage;
  encoded: EncodedState;
  calls: CallRecord[];
  prompt_mode: "compact" | "verbose";
};

export type MoveRequest = {
  player_id: string;
  moves_uci: string[];
  start_fen?: string | null;
  compact_prompt: boolean;
  max_retries: number;
};

export type Color = "white" | "black";

export type SideStats = {
  moves: number;
  costUsd: number;
  costKnown: boolean;
  latencyMsTotal: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  fallbacks: number;
};

export const emptyStats = (): SideStats => ({
  moves: 0,
  costUsd: 0,
  costKnown: true,
  latencyMsTotal: 0,
  inputTokens: 0,
  outputTokens: 0,
  cachedTokens: 0,
  fallbacks: 0,
});

export type PlyRecord = {
  ply: number;
  color: Color;
  san: string;
  uci: string;
  response: MoveResponse;
};
