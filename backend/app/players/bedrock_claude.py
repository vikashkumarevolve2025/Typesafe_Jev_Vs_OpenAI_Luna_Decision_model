"""Claude on Amazon Bedrock via the Converse API.

boto3 `converse` is called directly (not ChatBedrockConverse) so the Call Inspector can show
the exact request, the raw stopReason, cachePoint behaviour and cache token counts.
"""

from __future__ import annotations

import copy
import os
import time
from functools import cached_property
from typing import Any

import chess

from .. import config
from ..chess_state import parse_move_reply, render_compact, render_verbose
from ..pricing import cost_usd, has_price
from ..prompts import SYSTEM_PROMPT, build_user_prompt
from .base import CallRecord, Player, empty_usage


class BedrockClaudePlayer(Player):
    kind = "llm"
    group = "Anthropic Claude (Bedrock)"

    def __init__(
        self,
        id: str,
        label: str,
        model_id: str,
        price_key: str,
        *,
        max_tokens: int,
        request_fields: dict[str, Any],
    ):
        self.id = id
        self.label = label
        self.model_id = model_id
        self.price_key = price_key
        self.max_tokens = max_tokens
        # Sent as additionalModelRequestFields. The thinking config is always explicit, so a
        # model that thinks by default cannot silently spend the tiny answer budget on hidden reasoning.
        self.request_fields = request_fields

    # --- AWS plumbing -------------------------------------------------------------------
    @cached_property
    def _session(self):
        import boto3

        return boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.AWS_REGION)

    @cached_property
    def _client(self):
        from botocore.config import Config

        return self._session.client(
            "bedrock-runtime", config=Config(read_timeout=180, retries={"max_attempts": 2, "mode": "standard"})
        )

    def _reset_aws(self) -> None:
        self.__dict__.pop("_session", None)
        self.__dict__.pop("_client", None)

    def _reload_if_credentials_changed(self) -> None:
        """Pick up keys pasted into ~/.aws/credentials (or config) without restarting the server."""
        paths = [
            os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or os.path.expanduser("~/.aws/credentials"),
            os.environ.get("AWS_CONFIG_FILE") or os.path.expanduser("~/.aws/config"),
        ]
        stamp = tuple(os.path.getmtime(p) if os.path.exists(p) else None for p in paths)
        if stamp != getattr(self, "_creds_stamp", stamp):
            self._reset_aws()
        self._creds_stamp = stamp

    def availability(self) -> tuple[bool, str | None]:
        try:
            creds = self._session.get_credentials()
        except Exception as exc:  # profile not found, boto3 missing, …
            return False, f"AWS: {type(exc).__name__}"
        if creds is None:
            return False, "missing AWS credentials"
        return True, None if has_price(self.price_key) else "price unknown"

    # --- one move -------------------------------------------------------------------------
    def build_request(self, enc: dict[str, Any], compact: bool, feedback: str | None) -> dict[str, Any]:
        position = render_compact(enc) if compact else render_verbose(enc)
        system: list[dict[str, Any]] = [{"text": SYSTEM_PROMPT}]
        if config.BEDROCK_PROMPT_CACHE:
            system.append({"cachePoint": {"type": "default"}})
        return {
            "modelId": self.model_id,
            "system": system,
            "messages": [{"role": "user", "content": [{"text": build_user_prompt(position, feedback)}]}],
            "inferenceConfig": {"maxTokens": self.max_tokens},
            "additionalModelRequestFields": copy.deepcopy(self.request_fields),
        }

    def choose(self, board: chess.Board, enc: dict[str, Any], *, compact: bool, attempt: int, feedback: str | None) -> CallRecord:
        request = self.build_request(enc, compact, feedback)
        record = CallRecord(
            attempt=attempt,
            request=request,
            prompts={
                "system": SYSTEM_PROMPT,
                "user": request["messages"][0]["content"][0]["text"],
                "max_tokens": self.max_tokens,
                "thinking": request["additionalModelRequestFields"].get("thinking"),
                "output_config": request["additionalModelRequestFields"].get("output_config"),
            },
        )
        self._reload_if_credentials_changed()
        t0 = time.perf_counter()
        try:
            try:
                response = self._client.converse(**request)
            except Exception as exc:
                if "ExpiredToken" not in str(exc):
                    raise
                # Keys pasted into ~/.aws/credentials are temporary: drop the cached session so
                # refreshed keys are picked up without restarting the server, then retry once.
                self._reset_aws()
                response = self._client.converse(**request)
        except Exception as exc:
            record.latency_ms = (time.perf_counter() - t0) * 1000
            record.error = f"{type(exc).__name__}: {exc}"
            if "ExpiredToken" in str(exc):
                record.diagnosis = (
                    f"AWS credentials for profile '{config.AWS_PROFILE}' have expired. Refresh them "
                    "(aws sso login, or paste new keys into ~/.aws/credentials); no restart needed."
                )
            return record
        record.latency_ms = (time.perf_counter() - t0) * 1000

        text, reasoning_chars, reasoning_blocks = "", 0, 0
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                text += block["text"]
            elif "reasoningContent" in block:
                reasoning_blocks += 1
                rc = block["reasoningContent"]
                reasoning_chars += len(rc.get("reasoningText", {}).get("text", "")) if isinstance(rc, dict) else 0

        u = response.get("usage", {})
        record.usage = empty_usage() | {
            "input_tokens": u.get("inputTokens", 0),
            "output_tokens": u.get("outputTokens", 0),
            "cache_read_tokens": u.get("cacheReadInputTokens", 0),
            "cache_write_tokens": u.get("cacheWriteInputTokens", 0),
        }
        record.stop_reason = response.get("stopReason")
        record.cost_usd = cost_usd(self.price_key, record.usage)
        record.reply = self._redacted_reply(response)
        record.parsed_move = parse_move_reply(text, enc)

        if record.parsed_move is None:
            record.diagnosis = self._diagnose(text, record, reasoning_blocks, reasoning_chars)
        elif reasoning_blocks:
            record.diagnosis = (
                f"Model thought before answering ({reasoning_blocks} hidden reasoning block(s)); "
                f"{record.usage['output_tokens']} output tokens billed for a ~3-token answer."
            )
        return record

    def _diagnose(self, text: str, record: CallRecord, reasoning_blocks: int, reasoning_chars: int) -> str:
        out = record.usage["output_tokens"]
        if record.stop_reason == "max_tokens" and not text.strip():
            return (
                f"Hit max_tokens={self.max_tokens} with no visible text. {out} output tokens were spent before any "
                f"answer appeared — hidden thinking consumed the budget"
                + (f" ({reasoning_blocks} reasoning block(s), {reasoning_chars} chars)" if reasoning_blocks else "")
                + ". Fix: use the lowest thinking setting for move selection, or raise max_tokens well above the thinking budget."
            )
        if not text.strip():
            return f"Empty visible reply (stopReason={record.stop_reason})."
        return f"Reply {text.strip()[:60]!r} did not contain a valid move number or move."

    @staticmethod
    def _redacted_reply(response: dict[str, Any]) -> dict[str, Any]:
        reply = {k: v for k, v in response.items() if k != "ResponseMetadata"}
        reply = copy.deepcopy(reply)
        for block in reply.get("output", {}).get("message", {}).get("content", []):
            if "reasoningContent" in block:
                rc = block["reasoningContent"]
                n = len(rc.get("reasoningText", {}).get("text", "")) if isinstance(rc, dict) else 0
                block["reasoningContent"] = f"<hidden reasoning, {n} chars>"
        return reply
