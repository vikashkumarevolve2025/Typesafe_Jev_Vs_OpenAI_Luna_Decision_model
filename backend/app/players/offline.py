"""Offline baselines: no network, no cost. Useful as sparring partners and eval baselines."""

from __future__ import annotations

import random
import time
from typing import Any

import chess

from ..chess_state import PIECE_VALUES
from .base import CallRecord, Player


class RandomPlayer(Player):
    id = "random"
    label = "Random"
    group = "Offline"
    kind = "offline"

    def choose(self, board, enc, *, compact, attempt, feedback) -> CallRecord:
        t0 = time.perf_counter()
        move = random.choice(enc["legal_moves"])["uci"]
        return CallRecord(attempt=attempt, parsed_move=move, latency_ms=(time.perf_counter() - t0) * 1000)


def greedy_score(board: chess.Board, move: chess.Move) -> float:
    """One-ply heuristic: mate > captures by value > promotions > checks, minus hanging the mover."""
    score = 0.0
    mover = board.piece_at(move.from_square)
    if board.is_capture(move):
        victim = chess.PAWN if board.is_en_passant(move) else board.piece_at(move.to_square).piece_type
        score += PIECE_VALUES[victim] * 10
    if move.promotion:
        score += PIECE_VALUES[move.promotion] * 10
    board.push(move)
    try:
        if board.is_checkmate():
            return 10_000
        if board.is_check():
            score += 1
        # Penalise landing on a square the opponent attacks and we do not defend.
        attacked = board.is_attacked_by(board.turn, move.to_square)
        defended = board.is_attacked_by(not board.turn, move.to_square)
        if attacked and mover is not None:
            value = PIECE_VALUES[move.promotion or mover.piece_type]
            score -= value * (10 if not defended else 4)
    finally:
        board.pop()
    return score


class GreedyPlayer(Player):
    id = "greedy"
    label = "Greedy"
    group = "Offline"
    kind = "offline"

    def choose(self, board: chess.Board, enc: dict[str, Any], *, compact, attempt, feedback) -> CallRecord:
        t0 = time.perf_counter()
        scored = [(greedy_score(board, m) + random.random() * 0.01, m) for m in board.legal_moves]
        best = max(scored, key=lambda x: x[0])[1]
        return CallRecord(attempt=attempt, parsed_move=best.uci(), latency_ms=(time.perf_counter() - t0) * 1000)
