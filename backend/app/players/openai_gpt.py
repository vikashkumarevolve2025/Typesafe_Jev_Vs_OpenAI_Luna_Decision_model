"""OpenAI GPT models via the Responses API (POST /v1/responses).

Uses the same system prompt, user prompt and reply parser as the Claude players, so the
comparison is like-for-like. httpx is called directly so the Call Inspector shows the exact
request and the raw reply.
"""

from __future__ import annotations

import time
from functools import cached_property
from typing import Any

import chess
import httpx

from .. import config
from ..chess_state import parse_move_reply, render_compact, render_verbose
from ..pricing import cost_usd, has_price
from ..prompts import SYSTEM_PROMPT, build_user_prompt
from .base import CallRecord, Player, empty_usage


class OpenAIPlayer(Player):
    kind = "llm"
    group = "OpenAI"

    def __init__(self, id: str, label: str, model_id: str, price_key: str, *, max_tokens: int, reasoning_effort: str | None):
        self.id = id
        self.label = label
        self.model_id = model_id
        self.price_key = price_key
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort

    @cached_property
    def _http(self) -> httpx.Client:
        return httpx.Client(
            base_url=config.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
            timeout=180,
        )

    def availability(self) -> tuple[bool, str | None]:
        if not config.OPENAI_API_KEY:
            return False, "missing OPENAI_API_KEY"
        return True, None if has_price(self.price_key) else "price unknown"

    def build_request(self, enc: dict[str, Any], compact: bool, feedback: str | None) -> dict[str, Any]:
        position = render_compact(enc) if compact else render_verbose(enc)
        request: dict[str, Any] = {
            "model": self.model_id,
            "instructions": SYSTEM_PROMPT,
            "input": build_user_prompt(position, feedback),
            "max_output_tokens": self.max_tokens,
            "store": False,
        }
        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}
        return request

    def choose(self, board: chess.Board, enc: dict[str, Any], *, compact: bool, attempt: int, feedback: str | None) -> CallRecord:
        request = self.build_request(enc, compact, feedback)
        record = CallRecord(
            attempt=attempt,
            request=request,
            prompts={
                "system": request["instructions"],
                "user": request["input"],
                "max_tokens": self.max_tokens,
                "reasoning": request.get("reasoning"),
            },
        )
        t0 = time.perf_counter()
        try:
            resp = self._http.post("/v1/responses", json=request)
            record.latency_ms = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            record.latency_ms = (time.perf_counter() - t0) * 1000
            detail = getattr(getattr(exc, "response", None), "text", "")
            record.error = f"{type(exc).__name__}: {exc} {detail[:300]}".strip()
            if "billing_not_active" in detail:
                record.diagnosis = "OpenAI account has no active billing: add a payment method at platform.openai.com."
            return record

        record.reply = body
        record.stop_reason = body.get("status")
        text = "".join(
            part.get("text", "")
            for item in body.get("output", [])
            if item.get("type") == "message"
            for part in item.get("content", [])
        )
        u = body.get("usage", {})
        cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
        record.usage = empty_usage() | {
            # OpenAI counts cached tokens inside input_tokens; split them so each is priced once.
            "input_tokens": u.get("input_tokens", 0) - cached,
            "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": cached,
        }
        record.cost_usd = cost_usd(self.price_key, record.usage)
        record.parsed_move = parse_move_reply(text, enc)
        if record.parsed_move is None:
            reasoning = (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
            if body.get("status") == "incomplete" and not text.strip():
                record.diagnosis = (
                    f"Hit max_output_tokens={self.max_tokens} with no visible text "
                    f"({reasoning} reasoning tokens). Lower reasoning effort or raise OPENAI_MAX_TOKENS."
                )
            else:
                record.diagnosis = f"Reply {text.strip()[:60]!r} did not contain a valid move number or move."
        return record
