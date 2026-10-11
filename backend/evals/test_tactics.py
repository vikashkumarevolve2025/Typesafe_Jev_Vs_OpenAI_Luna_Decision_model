"""DeepEval suite: does each player find forcing moves, and does it always answer legally?

    EVAL_PLAYERS=greedy,random,jev,claude-sonnet-5.5 deepeval test run evals/test_tactics.py
    (or plain pytest)

Metrics are deterministic (no LLM judge), so results are cheap and reproducible apart
from the players themselves.
"""

from __future__ import annotations

import os

import chess
import pytest
from deepeval import assert_test
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

from app.graph import run_move
from app.players.registry import get_player

# (name, FEN, accepted best moves in UCI)
POSITIONS = [
    ("scholars_mate", "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", {"h5f7"}),
    ("back_rank_mate", "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1", {"e1e8"}),
    ("fools_mate_black", "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2", {"d8h4"}),
    ("free_queen", "q3k3/8/8/8/8/8/8/R5K1 w - - 0 1", {"a1a8"}),
]

PLAYERS = [p.strip() for p in os.getenv("EVAL_PLAYERS", "greedy,random").split(",") if p.strip()]


class LegalMoveMetric(BaseMetric):
    """1.0 if the player's own reply was legal (no fallback), else 0.0."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        meta = test_case.additional_metadata or {}
        self.score = 0.0 if meta.get("fallback") else 1.0
        self.reason = meta.get("fallback_reason") or "Player returned a legal move."
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Legal move"


class TacticFoundMetric(BaseMetric):
    """1.0 if the chosen move is one of the accepted best moves."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        accepted = set((test_case.expected_output or "").split(","))
        self.score = 1.0 if test_case.actual_output in accepted else 0.0
        self.reason = f"played {test_case.actual_output}, accepted {sorted(accepted)}"
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):
        return "Tactic found"


@pytest.mark.parametrize("player_id", PLAYERS)
@pytest.mark.parametrize("name,fen,best", POSITIONS, ids=[p[0] for p in POSITIONS])
def test_tactic(player_id: str, name: str, fen: str, best: set[str]):
    available, note = get_player(player_id).availability()
    if not available:
        pytest.skip(f"{player_id}: {note}")
    assert chess.Board(fen).is_valid()

    result = run_move(player_id, [], start_fen=fen, compact=True, max_retries=1)
    case = LLMTestCase(
        input=fen,
        actual_output=result["move_uci"],
        expected_output=",".join(sorted(best)),
        additional_metadata={
            "player": player_id,
            "fallback": result["fallback"],
            "fallback_reason": result["fallback_reason"],
            "latency_ms": sum(r.latency_ms for r in result["records"]),
        },
    )
    metrics = [LegalMoveMetric()]
    if player_id != "random":  # random is the floor, only checked for legality
        metrics.append(TacticFoundMetric())
    assert_test(case, metrics)
