"""The single dropdown: every selectable player, in display order."""

from __future__ import annotations

from .. import config
from .base import Player
from .bedrock_claude import BedrockClaudePlayer
from .jev import JevPlayer
from .offline import GreedyPlayer, RandomPlayer
from .openai_gpt import OpenAIPlayer

PLAYERS: dict[str, Player] = {
    p.id: p
    for p in [
        BedrockClaudePlayer(
            "claude-opus-5.5", "Claude Opus 5.5", config.OPUS_MODEL_ID, "OPUS",
            max_tokens=config.CLAUDE_FAST_MAX_TOKENS, request_fields=config.CLAUDE_FAST_FIELDS_OPUS,
        ),
        BedrockClaudePlayer(
            "claude-sonnet-5.5", "Claude Sonnet 5.5", config.SONNET_MODEL_ID, "SONNET",
            max_tokens=config.CLAUDE_FAST_MAX_TOKENS, request_fields=config.CLAUDE_FAST_FIELDS_SONNET,
        ),
        # Reproduces the debugging session: thinking on + a tiny answer budget.
        BedrockClaudePlayer(
            "claude-opus-5.5-thinking-bug", "Claude Opus 5.5 · thinking, 16-token budget (bug repro)",
            config.OPUS_MODEL_ID, "OPUS",
            max_tokens=config.CLAUDE_MAX_TOKENS, request_fields={"thinking": config.CLAUDE_THINKING_CONFIG},
        ),
        # The other fix: keep thinking but give it room.
        BedrockClaudePlayer(
            "claude-opus-5.5-thinking", "Claude Opus 5.5 · thinking (fixed budget)",
            config.OPUS_MODEL_ID, "OPUS",
            max_tokens=config.CLAUDE_THINKING_MAX_TOKENS, request_fields={"thinking": config.CLAUDE_THINKING_CONFIG},
        ),
        *(
            BedrockClaudePlayer(
                pid, label, model_id, price_key,
                max_tokens=config.CLAUDE_FAST_MAX_TOKENS, request_fields=config.CLAUDE_FAST_FIELDS_EXTRA,
            )
            for pid, label, model_id, price_key in config.CLAUDE_EXTRA_MODELS
        ),
        OpenAIPlayer(
            "openai", f"GPT ({config.OPENAI_MODEL})", config.OPENAI_MODEL, "OPENAI",
            max_tokens=config.OPENAI_MAX_TOKENS, reasoning_effort=config.OPENAI_REASONING_EFFORT,
        ),
        JevPlayer(),
        JevPlayer("jev-preview", "Jev Preview", config.JEV_PREVIEW_MODEL),
        # Same model, but code adds per-move safety facts (TypeSafe's "code does the calculation" pattern).
        JevPlayer("jev-facts", "Jev + move facts", config.JEV_MODEL, move_facts=True),
        GreedyPlayer(),
        RandomPlayer(),
    ]
}


def get_player(player_id: str) -> Player:
    try:
        return PLAYERS[player_id]
    except KeyError:
        raise KeyError(f"Unknown player '{player_id}'. Known: {', '.join(PLAYERS)}") from None
