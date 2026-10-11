"""Offline tests: no AWS or TypeSafe calls.  Run:  pytest -q"""

import chess
import pytest
from fastapi.testclient import TestClient

from app.chess_state import board_from_moves, encode, parse_move_reply, render_compact, render_verbose
from app.graph import run_move
from app.main import app
from app.players.jev import JevPlayer

client = TestClient(app)


def test_start_position_encoding():
    board, history = board_from_moves([])
    enc = encode(board, history)
    assert enc["side_to_move"] == "white"
    assert len(enc["legal_moves"]) == 20
    assert [m["n"] for m in enc["legal_moves"]] == list(range(1, 21))
    assert enc["material"] == {"white": 39, "black": 39, "balance": 0}
    assert len(enc["pieces"]) == 32


def test_compact_prompt_is_smaller():
    board, history = board_from_moves(["e2e4", "e7e5", "g1f3", "b8c6"])
    enc = encode(board, history)
    assert len(render_compact(enc)) < len(render_verbose(enc))
    assert "1.e4 e5 2.Nf3 Nc6" in render_compact(enc)


def test_illegal_history_rejected():
    with pytest.raises(ValueError):
        board_from_moves(["e2e5"])


def test_parse_reply_number_san_uci():
    board, history = board_from_moves([])
    enc = encode(board, history)
    e4 = next(m for m in enc["legal_moves"] if m["san"] == "e4")
    assert parse_move_reply(str(e4["n"]), enc) == "e2e4"
    assert parse_move_reply(" 21 ", enc) is None  # out of range
    assert parse_move_reply("I play Nf3", enc) == "g1f3"
    assert parse_move_reply("d2d4", enc) == "d2d4"
    assert parse_move_reply("", enc) is None


def test_mate_flag_scholars_mate():
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    enc = encode(board, [])
    mates = [m for m in enc["legal_moves"] if m["mate"]]
    assert [m["uci"] for m in mates] == ["h5f7"]


def test_greedy_finds_mate_in_one():
    moves = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6"]
    result = run_move("greedy", moves)
    assert result["move_uci"] == "h5f7"
    assert result["fallback"] is False


def test_jev_request_shape():
    board, history = board_from_moves([])
    req = JevPlayer().build_request(encode(board, history))
    move_q = req["questions"]["move"]
    assert move_q["type"] == "choice"
    assert len(move_q["criteria"]) == 20 and "e4" in move_q["criteria"]
    assert req["model"]


def test_api_players_and_move():
    ids = {p["id"] for p in client.get("/api/players").json()}
    assert {"jev", "claude-opus-5.5", "claude-sonnet-5.5", "greedy", "random"} <= ids
    r = client.post("/api/move", json={"player_id": "random", "moves_uci": ["e2e4"]})
    assert r.status_code == 200
    body = r.json()
    assert body["encoded"]["side_to_move"] == "black"
    assert body["move_uci"] in {m["uci"] for m in body["encoded"]["legal_moves"]}
    assert body["calls"] == [] and body["cost_usd"] == 0.0


def test_full_offline_game_terminates():
    moves: list[str] = []
    board = chess.Board()
    while not board.is_game_over() and len(moves) < 200:
        pid = "greedy" if board.turn == chess.WHITE else "random"
        uci = client.post("/api/move", json={"player_id": pid, "moves_uci": moves}).json()["move_uci"]
        board.push_uci(uci)
        moves.append(uci)
    assert len(moves) > 0
