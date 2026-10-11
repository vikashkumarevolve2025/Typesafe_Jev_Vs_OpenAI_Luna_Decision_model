"""FastAPI entrypoint.  Run:  uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import chess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from . import observability as obs
from .chess_state import board_from_moves, encode, render_compact, render_verbose
from .graph import run_move
from .players.base import empty_usage
from .players.registry import PLAYERS, get_player

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    obs.flush()


app = FastAPI(title="LLM Chess Arena", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


class MoveRequest(BaseModel):
    player_id: str
    moves_uci: list[str] = Field(default_factory=list)
    start_fen: str | None = None
    compact_prompt: bool = True
    max_retries: int = Field(default=1, ge=0, le=3)


class EncodeRequest(BaseModel):
    moves_uci: list[str] = Field(default_factory=list)
    start_fen: str | None = None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/players")
def players() -> list[dict[str, Any]]:
    return [p.info() for p in PLAYERS.values()]


@app.post("/api/encode")
def encode_position(req: EncodeRequest) -> dict[str, Any]:
    """Preview the structured state and both prompt renderings (handy for prompt-size comparisons)."""
    try:
        board, history = board_from_moves(req.moves_uci, req.start_fen)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    enc = encode(board, history)
    compact, verbose = render_compact(enc), render_verbose(enc)
    return {
        "encoded": enc,
        "compact_prompt": compact,
        "verbose_prompt": verbose,
        "chars": {"compact": len(compact), "verbose": len(verbose)},
    }


@app.post("/api/move")
def move(req: MoveRequest) -> dict[str, Any]:
    # Sync def: FastAPI runs it in a worker thread, so blocking boto3/httpx calls are fine.
    try:
        player = get_player(req.player_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    available, note = player.availability()
    if not available:
        raise HTTPException(400, f"{player.label} is not available: {note}")

    try:
        result = run_move(
            req.player_id, req.moves_uci, start_fen=req.start_fen, compact=req.compact_prompt, max_retries=req.max_retries
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        # Surface the real cause in the UI instead of a bare "Internal Server Error".
        log.exception("move failed for %s", req.player_id)
        raise HTTPException(502, f"{player.label}: {type(exc).__name__}: {exc}") from exc

    records = result["records"]
    usage = empty_usage()
    for r in records:
        for k in usage:
            usage[k] += r.usage.get(k, 0)
    costs = [r.cost_usd for r in records if r.request is not None]
    cost = None if any(c is None for c in costs) else sum(c for c in costs)  # type: ignore[misc]
    if player.kind == "offline":
        cost = 0.0

    board = chess.Board(result["fen"])
    move_obj = chess.Move.from_uci(result["move_uci"])
    return {
        "player": player.info(),
        "move_uci": result["move_uci"],
        "move_san": board.san(move_obj),
        "fallback": result["fallback"],
        "fallback_reason": result["fallback_reason"],
        "latency_ms": sum(r.latency_ms for r in records),
        "cost_usd": cost,
        "usage": usage,
        "encoded": result["encoded"],
        "calls": [r.to_dict() for r in records if r.request is not None],
        "prompt_mode": "compact" if req.compact_prompt else "verbose",
    }
