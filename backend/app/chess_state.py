"""Turn a chess position into structured, model-ready information.

State  ->  {pieces, numbered legal moves, material, history}  ->  prompt text / Jev criteria
"""

from __future__ import annotations

import re
from typing import Any

import chess

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
COLOR_NAME = {chess.WHITE: "white", chess.BLACK: "black"}


def board_from_moves(moves_uci: list[str], start_fen: str | None = None) -> tuple[chess.Board, list[str]]:
    """Replay UCI moves from the start position; returns the board and SAN history."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    history: list[str] = []
    for i, uci in enumerate(moves_uci):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move #{i + 1}: {uci} in {board.fen()}")
        history.append(board.san(move))
        board.push(move)
    return board, history


def material(board: chess.Board) -> dict[str, int]:
    totals = {chess.WHITE: 0, chess.BLACK: 0}
    for piece in board.piece_map().values():
        totals[piece.color] += PIECE_VALUES[piece.piece_type]
    return {"white": totals[chess.WHITE], "black": totals[chess.BLACK], "balance": totals[chess.WHITE] - totals[chess.BLACK]}


def _captured_piece(board: chess.Board, move: chess.Move) -> str | None:
    if not board.is_capture(move):
        return None
    if board.is_en_passant(move):
        return "pawn"
    victim = board.piece_at(move.to_square)
    return PIECE_NAMES[victim.piece_type] if victim else None


def legal_choices(board: chess.Board) -> list[dict[str, Any]]:
    """All legal moves as numbered choices, sorted by SAN so numbering is stable."""
    items = []
    for move in board.legal_moves:
        san = board.san(move)
        mover = board.piece_at(move.from_square)
        items.append(
            {
                "uci": move.uci(),
                "san": san,
                "piece": PIECE_NAMES[mover.piece_type] if mover else "?",
                "from": chess.square_name(move.from_square),
                "to": chess.square_name(move.to_square),
                "capture": _captured_piece(board, move),
                "check": san.endswith(("+", "#")),
                "mate": san.endswith("#"),
                "promotion": PIECE_NAMES[move.promotion] if move.promotion else None,
            }
        )
    items.sort(key=lambda m: m["san"])
    for n, item in enumerate(items, start=1):
        item["n"] = n
    return items


def encode(board: chess.Board, history_san: list[str]) -> dict[str, Any]:
    pieces = [
        {"square": chess.square_name(sq), "piece": PIECE_NAMES[p.piece_type], "color": COLOR_NAME[p.color]}
        for sq, p in sorted(board.piece_map().items(), key=lambda kv: (not kv[1].color, -PIECE_VALUES[kv[1].piece_type] if kv[1].piece_type != chess.KING else -100, kv[0]))
    ]
    return {
        "fen": board.fen(),
        "side_to_move": COLOR_NAME[board.turn],
        "move_number": board.fullmove_number,
        "in_check": board.is_check(),
        "pieces": pieces,
        "legal_moves": legal_choices(board),
        "material": material(board),
        "history_san": history_san,
    }


def format_history(history_san: list[str], last_n_plies: int | None = None) -> str:
    if not history_san:
        return "(none)"
    start = 0 if last_n_plies is None else max(0, len(history_san) - last_n_plies)
    if start % 2:  # begin on a white move so numbering stays correct
        start -= 1
    parts = []
    for i in range(start, len(history_san), 2):
        pair = history_san[i : i + 2]
        parts.append(f"{i // 2 + 1}.{' '.join(pair)}")
    prefix = "… " if start > 0 else ""
    return prefix + " ".join(parts)


def _describe_move(m: dict[str, Any]) -> str:
    desc = f"{m['piece']} {m['from']}->{m['to']}"
    if m["capture"]:
        desc += f", captures {m['capture']}"
    if m["promotion"]:
        desc += f", promotes to {m['promotion']}"
    if m["mate"]:
        desc += ", CHECKMATE"
    elif m["check"]:
        desc += ", check"
    return desc


def describe_move(m: dict[str, Any]) -> str:
    return _describe_move(m)


# --- Move facts: one-ply tactical checks done in code, so a System One model judges facts
# instead of calculating. Approximate (static, no full exchange search), stated in words
# because Jev handles numbers poorly.

_MATERIAL_WORDS = [(9, "a queen"), (5, "a rook"), (3, "a minor piece"), (2, "two pawns"), (1, "a pawn")]


def _material_words(value: int) -> str:
    return next((w for v, w in _MATERIAL_WORDS if value >= v), "nothing")


def _exposure(board: chess.Board, square: chess.Square) -> int:
    """How much the piece on `square` can lose to one capture by the side to move."""
    piece = board.piece_at(square)
    attackers = board.attackers(not piece.color, square)
    if not attackers:
        return 0
    value = PIECE_VALUES[piece.piece_type]
    if not board.attackers(piece.color, square):
        return value
    cheapest = min(PIECE_VALUES[board.piece_at(a).piece_type] or 100 for a in attackers)
    return max(0, value - cheapest)


def move_facts(board: chess.Board, move: chess.Move) -> list[str]:
    us = board.turn
    gained = PIECE_VALUES[chess.PAWN] if board.is_en_passant(move) else (
        PIECE_VALUES[board.piece_at(move.to_square).piece_type] if board.is_capture(move) else 0
    )
    if move.promotion:
        gained += PIECE_VALUES[move.promotion] - PIECE_VALUES[chess.PAWN]
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return ["checkmate: wins the game"]

    facts: list[str] = []
    for reply in after.legal_moves:
        after.push(reply)
        mated = after.is_checkmate()
        after.pop()
        if mated:
            facts.append("BLUNDER: lets the opponent checkmate on the next move")
            break

    worst, worst_sq = 0, None
    for sq, p in after.piece_map().items():
        if p.color == us and p.piece_type != chess.KING:
            loss = _exposure(after, sq)
            if loss > worst:
                worst, worst_sq = loss, sq
    if worst_sq is not None:
        name = PIECE_NAMES[after.piece_at(worst_sq).piece_type]
        where = "the moved" if worst_sq == move.to_square else f"your {chess.square_name(worst_sq)}"
        facts.append(f"leaves {where} {name} hanging (opponent can win {_material_words(worst)})")

    net = gained - worst
    if net > 0:
        facts.append(f"net result: wins {_material_words(net)}")
    elif net < 0:
        facts.append(f"net result: loses {_material_words(-net)}")
    elif not facts:
        facts.append("safe: nothing left hanging")
    else:
        facts.append("net result: material stays even")
    return facts


def describe_move_with_facts(board: chess.Board, m: dict[str, Any]) -> str:
    return f"{_describe_move(m)}. " + "; ".join(move_facts(board, chess.Move.from_uci(m["uci"])))


def render_compact(enc: dict[str, Any]) -> str:
    """Small prompt: FEN + material + recent history + numbered SAN list."""
    mat = enc["material"]
    moves = " ".join(f"{m['n']}:{m['san']}" for m in enc["legal_moves"])
    return (
        f"FEN {enc['fen']}\n"
        f"To move: {enc['side_to_move']}{' (in check)' if enc['in_check'] else ''}\n"
        f"Material W{mat['white']} B{mat['black']}\n"
        f"Recent: {format_history(enc['history_san'], last_n_plies=12)}\n"
        f"Moves: {moves}"
    )


def render_verbose(enc: dict[str, Any]) -> str:
    """Large prompt: every piece, full history and a described move list."""
    by_color: dict[str, list[str]] = {"white": [], "black": []}
    for p in enc["pieces"]:
        by_color[p["color"]].append(f"{p['piece']} {p['square']}")
    mat = enc["material"]
    lines = [
        f"Position (FEN): {enc['fen']}",
        f"Side to move: {enc['side_to_move']}, move {enc['move_number']}. In check: {'yes' if enc['in_check'] else 'no'}.",
        f"White pieces: {', '.join(by_color['white'])}",
        f"Black pieces: {', '.join(by_color['black'])}",
        f"Material: white {mat['white']}, black {mat['black']} (balance {mat['balance']:+d} for white)",
        f"Move history: {format_history(enc['history_san'])}",
        "Legal moves (choose one by number):",
    ]
    lines += [f"{m['n']}. {m['san']} — {_describe_move(m)}" for m in enc["legal_moves"]]
    return "\n".join(lines)


def render_state_for_jev(enc: dict[str, Any]) -> str:
    """State text for Jev. The moves themselves go in the Choice criteria, not here."""
    by_color: dict[str, list[str]] = {"white": [], "black": []}
    for p in enc["pieces"]:
        by_color[p["color"]].append(f"{p['piece']} {p['square']}")
    mat = enc["material"]
    return "\n".join(
        [
            f"Chess position. {enc['side_to_move'].capitalize()} to move (move {enc['move_number']})."
            + (" The side to move is in check." if enc["in_check"] else ""),
            f"FEN: {enc['fen']}",
            f"White pieces: {', '.join(by_color['white'])}",
            f"Black pieces: {', '.join(by_color['black'])}",
            f"Material: white {mat['white']}, black {mat['black']}",
            f"Recent moves: {format_history(enc['history_san'], last_n_plies=16)}",
        ]
    )


_NUM = re.compile(r"\b(\d{1,3})\b")
_MOVE_MARK = re.compile(r"MOVE\s*:?\s*#?(\d{1,3})\b", re.IGNORECASE)


def parse_move_reply(text: str, enc: dict[str, Any]) -> str | None:
    """Map a model reply to a legal UCI move: a final "MOVE: n" line first, then the first
    choice number, then SAN/UCI text."""
    if not text:
        return None
    legal = enc["legal_moves"]
    marks = _MOVE_MARK.findall(text)
    if marks and 1 <= int(marks[-1]) <= len(legal):
        return legal[int(marks[-1]) - 1]["uci"]
    match = _NUM.search(text)
    if match:
        n = int(match.group(1))
        if 1 <= n <= len(legal):
            return legal[n - 1]["uci"]
    tokens = re.findall(r"[A-Za-z0-9=+#\-]+", text)
    by_san = {m["san"].rstrip("+#"): m["uci"] for m in legal}
    by_uci = {m["uci"]: m["uci"] for m in legal}
    for tok in tokens:
        clean = tok.rstrip("+#")
        if clean in by_san:
            return by_san[clean]
        if tok.lower() in by_uci:
            return by_uci[tok.lower()]
    return None
