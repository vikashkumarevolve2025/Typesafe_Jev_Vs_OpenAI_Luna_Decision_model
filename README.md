# LLM Chess Arena

Pick two players, press **Play**, and watch them play — with latency, cost, tokens,
cache hits and the exact data sent to each model on every move.

```
State → Choices → Decision → Move → New State   (repeated every ply)
```

| Player | How it decides |
|---|---|
| Claude Opus 5.5 / Sonnet 5.5 (Bedrock) | Generative: reads a prompt, replies with a move **number** |
| Claude Opus 5.5 · thinking, 16-token budget | Reproduces the "hidden thinking ate the budget" bug |
| Claude Opus 5.5 · thinking (fixed budget) | Thinking kept, `max_tokens` raised |
| Claude Sonnet 5 / 4.6 / 4.5, Haiku 5.5 / 4.5 (Bedrock) | Smaller / earlier models for comparison, thinking disabled; IDs via `BEDROCK_<MODEL>_MODEL_ID`, prices via `PRICE_<MODEL>_*` |
| Jev (TypeSafe System One) | One **Choice** question whose options are the legal moves, plus Score/Noul signals |
| Greedy, Random | Offline baselines (no network, $0) |

## Layout

```
frontend/   Next.js 15 + react-chessboard v5 + chess.js
  components/Arena.tsx         game loop (one /api/move call per ply), Play/Stop/Reset/Swap
  components/PlayerCard.tsx    single grouped dropdown, cost/latency/token/cache metrics, move list
  components/CallInspector.tsx Data sent · Prompts · Reply & usage, per ply and per retry attempt
backend/    FastAPI + LangGraph
  app/chess_state.py           board → pieces, numbered legal moves, material, history; compact/verbose renderers
  app/graph.py                 LangGraph: encode → decide → validate → (retry | accept | fallback)
  app/players/bedrock_claude.py  boto3 Converse: cachePoint, explicit thinking config, stopReason diagnosis
  app/players/jev.py           POST /v1/systemone with Choice + Score + Noul questions
  app/players/offline.py       Greedy, Random
  app/prompts.py               LangChain PromptTemplates (static system prompt for caching)
  app/pricing.py               USD / 1M tokens from env → cost per move and per game
  app/observability.py         Langfuse v3 spans + generations (no-op without keys)
  tests/test_arena.py          offline unit + API tests
  evals/test_tactics.py        DeepEval: legal-move rate and tactic-found rate per player
```

## Run it

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in TYPESAFE_API_KEY, AWS_PROFILE, prices, Langfuse keys
aws sso login --profile foresight                       # or however you normally get Bedrock creds
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                  # http://localhost:3000  (proxies /api/* to :8000; override with BACKEND_URL)
```

Tests and evals:

```bash
cd backend
pytest -q tests/                                   # offline, no API calls
EVAL_PLAYERS=greedy,jev,claude-sonnet-5.5 deepeval test run evals/test_tactics.py
```

## How the state reaches each model

`/api/move` receives the UCI move list, replays it with python-chess and builds:

```json
{ "fen": "...", "side_to_move": "white", "in_check": false,
  "pieces": [{"square": "e1", "piece": "king", "color": "white"}, ...],
  "legal_moves": [{"n": 1, "san": "Bxf7#", "uci": "c4f7", "piece": "bishop", "capture": "pawn", "mate": true}, ...],
  "material": {"white": 39, "black": 39, "balance": 0},
  "history_san": ["e4", "e5", ...] }
```

- **Claude (compact prompt)**: FEN, material, last 12 plies, `1:Bxf7# 2:Kd1 …`. Reply = one number, `maxTokens=16`.
- **Claude (verbose prompt)**: every piece by square, full history, one described line per move. Toggle *Compact prompt* in the UI and compare tokens per move.
- **Jev**: the position text is the `state`; the legal moves are the `criteria` of a Choice question
  (option names are SAN, descriptions add piece/capture/check). In the same call: a Score question
  (position eval) and Noul questions (own piece hanging, mate threat, can win material). The
  probabilities over moves and the signals appear under *Reply & usage → Decision signals*.

## The thinking-budget bug (and the fix)

Symptom: Opus kept playing what looked like random moves.
The Inspector showed `stopReason: max_tokens`, output tokens = 16, and **no text block** —
so the parser found no number and the graph fell back to a random legal move.

Cause: thinking was on, and hidden reasoning tokens count against `maxTokens`. A 16-token
budget sized for a 3-token answer was used up before any visible text appeared.

Fixes, both selectable in the dropdown:
1. Send `thinking: {"type": "disabled"}` explicitly for move selection (default for the main Claude players).
2. Keep thinking but raise `maxTokens` (`CLAUDE_THINKING_MAX_TOKENS`, default 4096) — better moves, more cost and latency.

`bedrock_claude.py` detects the pattern (`stopReason == "max_tokens"` + empty visible text) and
writes the diagnosis into the call record, so it shows in the Inspector and in Langfuse.

## Cost, caching, retries

- Prices are read from `.env` (`PRICE_OPUS_IN`, …) — fill them from the Bedrock pricing page for your region.
  Unset prices show as "price unknown" and the game cost is marked with `*`.
- The static system prompt sits before a Bedrock `cachePoint`. Bedrock only caches a prefix above the
  model's minimum cacheable length, so with the short system prompt cache reads stay at 0; it starts
  paying off if you grow the static prefix (rules, examples). Cache read/write tokens are tracked either way.
- *Retries on invalid reply* (0–2): the graph re-asks with a short correction before falling back.
  Every attempt is kept and shown as a separate tab in the Inspector.

## Langfuse & DeepEval

- Set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`. Each move becomes a `chess.move`
  span with one generation per attempt (usage incl. cache tokens, cost, latency, diagnosis, Jev signals).
- `evals/test_tactics.py` runs mate-in-one and free-material positions through the same LangGraph and
  scores two deterministic DeepEval metrics: *Legal move* (no fallback) and *Tactic found*.

## Notes

- Model IDs default to `us.anthropic.claude-opus-5-5` / `us.anthropic.claude-sonnet-5-5`; override with
  `BEDROCK_OPUS_MODEL_ID` / `BEDROCK_MODEL_ID` if your inference profile IDs differ.
- If your Opus model rejects the thinking config, set `CLAUDE_THINKING_CONFIG` (JSON) — e.g.
  `{"type": "enabled", "budget_tokens": 1024}` (then `CLAUDE_THINKING_MAX_TOKENS` must be larger than the budget).
- Never commit `backend/.env`.
