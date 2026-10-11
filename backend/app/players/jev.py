"""Jev (TypeSafe System One) as a chess player.

The position is the *state*; the legal moves are the options of one Choice question.
Score and Noul questions ride along in the same call as extra decision signals.
Docs: https://docs.typesafe.ai  (POST /v1/systemone)
"""

from __future__ import annotations

import time
from functools import cached_property
from typing import Any

import chess
import httpx

from .. import config
from ..chess_state import describe_move, describe_move_with_facts, render_state_for_jev
from ..pricing import cost_usd, has_price
from .base import CallRecord, Player

MAX_CHOICE_OPTIONS = 255  # Choice limit per the TypeSafe docs; chess never exceeds 218 legal moves.

SIGNAL_QUESTIONS: dict[str, dict[str, Any]] = {
    "eval": {
        "type": "score",
        "instructions": "How good is this position for the side to move?",
        "criteria": [
            "Losing: down significant material or facing mate",
            "Worse: clearly behind",
            "Roughly equal",
            "Better: clearly ahead",
            "Winning: decisive advantage or mate available",
        ],
    },
    "own_piece_hanging": {
        "type": "noul",
        "instructions": "The side to move has a piece that is attacked and not adequately defended.",
    },
    "mate_threat": {
        "type": "noul",
        "instructions": "The opponent is threatening checkmate on their next move.",
    },
    "can_win_material": {
        "type": "noul",
        "instructions": "The side to move can win material with a capture right now.",
    },
}


class JevPlayer(Player):
    group = "System One"
    kind = "system_one"

    def __init__(self, id: str = "jev", label: str = "Jev", model_id: str | None = None, *, move_facts: bool = False):
        self.id = id
        self.model_id = model_id or config.JEV_MODEL
        # move_facts: code computes each move's safety (hanging pieces, mate threats, net material)
        # and adds it to the option description, so Jev judges facts instead of calculating.
        self.move_facts = move_facts
        # Show the model alias in the dropdown, e.g. "Jev (jev-latest)".
        self.label = f"{label} ({self.model_id})"

    @cached_property
    def _http(self) -> httpx.Client:
        return httpx.Client(
            base_url=config.TYPESAFE_BASE_URL,
            headers={"Authorization": f"Bearer {config.TYPESAFE_API_KEY}", "Content-Type": "application/json"},
            timeout=60,
        )

    def availability(self) -> tuple[bool, str | None]:
        if not config.TYPESAFE_API_KEY:
            return False, "missing TYPESAFE_API_KEY"
        return True, None if has_price("JEV") else "price unknown"

    def build_request(self, enc: dict[str, Any], board: chess.Board | None = None) -> dict[str, Any]:
        side = enc["side_to_move"]
        moves = enc["legal_moves"][:MAX_CHOICE_OPTIONS]
        # Option names are SAN, so Jev sees "Bxf7#" rather than an opaque id; descriptions add the facts.
        if self.move_facts:
            board = board or chess.Board(enc["fen"])
            criteria = {m["san"]: describe_move_with_facts(board, m) for m in moves}
            priorities = (
                "Checkmate if available. Never choose a move marked BLUNDER. Prefer the move whose net result "
                "wins the most material; avoid moves whose net result loses material or that leave a piece "
                "hanging. Among safe moves, improve piece activity and king safety."
            )
        else:
            criteria = {m["san"]: describe_move(m) for m in moves}
            priorities = (
                "Checkmate if available; otherwise win material safely; never leave pieces "
                "undefended; then improve piece activity and king safety."
            )
        questions: dict[str, Any] = {
            "move": {
                "type": "choice",
                "instructions": {
                    "question": f"Which move is strongest for {side} in this position?",
                    "priorities": priorities,
                },
                "criteria": criteria,
            }
        }
        if config.JEV_SIGNALS:
            questions.update(SIGNAL_QUESTIONS)
        return {"state": render_state_for_jev(enc), "model": self.model_id, "questions": questions}

    def choose(self, board: chess.Board, enc: dict[str, Any], *, compact: bool, attempt: int, feedback: str | None) -> CallRecord:
        request = self.build_request(enc, board)
        record = CallRecord(
            attempt=attempt,
            request=request,
            prompts={"state": request["state"], "questions": request["questions"]},
        )
        t0 = time.perf_counter()
        try:
            resp = self._http.post("/v1/systemone", json=request)
            record.latency_ms = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            record.latency_ms = (time.perf_counter() - t0) * 1000
            detail = getattr(getattr(exc, "response", None), "text", "")
            record.error = f"{type(exc).__name__}: {exc} {detail[:300]}".strip()
            return record

        record.reply = body
        record.stop_reason = "answered"
        usage = body.get("usage", {})
        record.usage["input_tokens"] = usage.get("input_tokens", 0)
        record.usage["output_tokens"] = usage.get("output_tokens", 0)
        record.cost_usd = cost_usd("JEV", record.usage)

        answers = body.get("answers", {})
        move_ans = answers.get("move", {})
        san_to_uci = {m["san"]: m["uci"] for m in enc["legal_moves"]}
        record.parsed_move = san_to_uci.get(move_ans.get("choice"))
        if record.parsed_move is None:
            record.diagnosis = f"Jev choice {move_ans.get('choice')!r} not in the legal move list."

        probs = move_ans.get("probabilities", {}) or {}
        top = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:5]
        signals: dict[str, Any] = {
            "choice": move_ans.get("choice"),
            "choice_confidence": move_ans.get("confidence"),
            "top_moves": [{"san": s, "p": p} for s, p in top],
        }
        if "eval" in answers:
            signals["eval_score"] = answers["eval"].get("score")
            signals["eval_confidence"] = answers["eval"].get("confidence")
            signals["eval_label"] = (answers["eval"].get("legend") or {}).get(
                str(int(round(answers["eval"].get("score", 0) or 0)))
            )
        for key in ("own_piece_hanging", "mate_threat", "can_win_material"):
            if key in answers:
                signals[key] = answers[key].get("noul")
        record.signals = signals
        return record
