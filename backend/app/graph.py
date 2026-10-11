"""One move as a LangGraph:  encode -> decide -> validate -> (retry | accept | fallback)

    State -> Choices -> Decision -> Move   (the arena repeats this per ply)
"""

from __future__ import annotations

import random
from typing import Any, TypedDict

import chess
from langgraph.graph import END, START, StateGraph

from . import observability as obs
from .chess_state import board_from_moves, encode
from .players.base import CallRecord
from .players.registry import get_player


class MoveState(TypedDict, total=False):
    # inputs
    player_id: str
    moves_uci: list[str]
    start_fen: str | None
    compact: bool
    max_retries: int
    # derived
    fen: str
    encoded: dict[str, Any]
    attempt: int
    feedback: str | None
    records: list[CallRecord]
    candidate: str | None
    decision: str
    # outputs
    move_uci: str
    fallback: bool
    fallback_reason: str | None


def node_encode(state: MoveState) -> MoveState:
    board, history = board_from_moves(state["moves_uci"], state.get("start_fen"))
    if board.is_game_over():
        raise ValueError(f"Game is already over: {board.result()}")
    return {"fen": board.fen(), "encoded": encode(board, history), "attempt": 0, "records": [], "feedback": None}


def node_decide(state: MoveState) -> MoveState:
    player = get_player(state["player_id"])
    attempt = state["attempt"] + 1
    board = chess.Board(state["fen"])
    with obs.generation(
        f"{player.id}.choose",
        model=getattr(player, "model_id", None) or player.id,
        input={"fen": state["fen"], "compact": state["compact"], "attempt": attempt},
        metadata={"player": player.id, "kind": player.kind},
    ) as gen:
        record = player.choose(
            board, state["encoded"], compact=state["compact"], attempt=attempt, feedback=state.get("feedback")
        )
        obs.safe_update(
            gen,
            output={"move": record.parsed_move, "stop_reason": record.stop_reason, "error": record.error},
            usage_details={
                "input": record.usage["input_tokens"],
                "output": record.usage["output_tokens"],
                "cache_read_input_tokens": record.usage["cache_read_tokens"],
                "cache_creation_input_tokens": record.usage["cache_write_tokens"],
            },
            cost_details={"total": record.cost_usd} if record.cost_usd is not None else None,
            metadata={"latency_ms": record.latency_ms, "diagnosis": record.diagnosis, "signals": record.signals},
        )
    return {"attempt": attempt, "records": [*state["records"], record], "candidate": record.parsed_move}


def node_validate(state: MoveState) -> MoveState:
    legal = {m["uci"] for m in state["encoded"]["legal_moves"]}
    cand = state.get("candidate")
    if cand in legal:
        return {"decision": "accept"}
    player = get_player(state["player_id"])
    last = state["records"][-1]
    if player.kind != "offline" and last.error is None and state["attempt"] <= state["max_retries"]:
        return {"decision": "retry", "feedback": "no move number found" if cand is None else f"{cand} is illegal"}
    return {"decision": "fallback"}


def node_accept(state: MoveState) -> MoveState:
    return {"move_uci": state["candidate"], "fallback": False, "fallback_reason": None}


def node_fallback(state: MoveState) -> MoveState:
    last = state["records"][-1]
    reason = last.error or last.diagnosis or "no valid move in reply"
    move = random.choice(state["encoded"]["legal_moves"])["uci"]
    return {"move_uci": move, "fallback": True, "fallback_reason": f"random legal move after {state['attempt']} attempt(s): {reason}"}


def _route(state: MoveState) -> str:
    return state["decision"]


def build_graph():
    g = StateGraph(MoveState)
    g.add_node("encode", node_encode)
    g.add_node("decide", node_decide)
    g.add_node("validate", node_validate)
    g.add_node("accept", node_accept)
    g.add_node("fallback", node_fallback)
    g.add_edge(START, "encode")
    g.add_edge("encode", "decide")
    g.add_edge("decide", "validate")
    g.add_conditional_edges("validate", _route, {"retry": "decide", "accept": "accept", "fallback": "fallback"})
    g.add_edge("accept", END)
    g.add_edge("fallback", END)
    return g.compile()


MOVE_GRAPH = build_graph()


def run_move(player_id: str, moves_uci: list[str], *, start_fen: str | None = None, compact: bool = True, max_retries: int = 1) -> MoveState:
    inputs: MoveState = {
        "player_id": player_id,
        "moves_uci": moves_uci,
        "start_fen": start_fen,
        "compact": compact,
        "max_retries": max_retries,
    }
    with obs.span("chess.move", input={"player": player_id, "ply": len(moves_uci)}) as s:
        result: MoveState = MOVE_GRAPH.invoke(inputs)
        obs.safe_update(s, output={"move": result.get("move_uci"), "fallback": result.get("fallback")})
    return result
