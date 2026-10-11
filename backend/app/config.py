"""Environment-driven settings. Loads backend/.env if present."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def env_float(name: str) -> float | None:
    value = env(name)
    return float(value) if value is not None else None


def env_int(name: str, default: int) -> int:
    value = env(name)
    return int(value) if value is not None else default


def env_bool(name: str, default: bool) -> bool:
    value = env(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_json(name: str, default: dict) -> dict:
    value = env(name)
    return json.loads(value) if value else default


TYPESAFE_API_KEY = env("TYPESAFE_API_KEY")
TYPESAFE_BASE_URL = env("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
JEV_MODEL = env("JEV_MODEL", "jev-latest")
JEV_PREVIEW_MODEL = env("JEV_PREVIEW_MODEL", "jev-preview")
JEV_SIGNALS = env_bool("JEV_SIGNALS", True)

AWS_REGION = env("AWS_REGION", "us-east-1")
AWS_PROFILE = env("AWS_PROFILE")
SONNET_MODEL_ID = env("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-5-5")
OPUS_MODEL_ID = env("BEDROCK_OPUS_MODEL_ID", "us.anthropic.claude-opus-5-5")
BEDROCK_PROMPT_CACHE = env_bool("BEDROCK_PROMPT_CACHE", True)
CLAUDE_MAX_TOKENS = env_int("CLAUDE_MAX_TOKENS", 16)
# Budget for the normal Opus/Sonnet players. Thinking cannot be switched off on these models,
# so they need room for a little reasoning before the "MOVE: n" line.
CLAUDE_FAST_MAX_TOKENS = env_int("CLAUDE_FAST_MAX_TOKENS", 512)
CLAUDE_THINKING_MAX_TOKENS = env_int("CLAUDE_THINKING_MAX_TOKENS", 4096)
CLAUDE_THINKING_CONFIG = env_json("CLAUDE_THINKING_CONFIG", {"type": "adaptive"})
# Bedrock additionalModelRequestFields for the normal (minimal-thinking) players. These models
# reject {"type": "disabled"}: Sonnet's lowest setting is "between_tools", Opus only takes
# "adaptive" plus a low output_config.effort.
CLAUDE_FAST_FIELDS_OPUS = env_json(
    "CLAUDE_FAST_FIELDS_OPUS", {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
)
CLAUDE_FAST_FIELDS_SONNET = env_json("CLAUDE_FAST_FIELDS_SONNET", {"thinking": {"type": "between_tools"}})

# Smaller / earlier Claude models for comparison. All of these accept thinking "disabled".
# (player id, label, Bedrock inference profile, price key -> PRICE_<key>_IN / _OUT / ...)
CLAUDE_EXTRA_MODELS = [
    ("claude-sonnet-5", "Claude Sonnet 5", env("BEDROCK_SONNET5_MODEL_ID", "us.anthropic.claude-sonnet-5"), "SONNET5"),
    ("claude-sonnet-4.6", "Claude Sonnet 4.6", env("BEDROCK_SONNET46_MODEL_ID", "us.anthropic.claude-sonnet-4-6"), "SONNET46"),
    (
        "claude-sonnet-4.5", "Claude Sonnet 4.5",
        env("BEDROCK_SONNET45_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"), "SONNET45",
    ),
    ("claude-haiku-5.5", "Claude Haiku 5.5", env("BEDROCK_HAIKU55_MODEL_ID", "us.anthropic.claude-haiku-5-5"), "HAIKU55"),
    (
        "claude-haiku-4.5", "Claude Haiku 4.5",
        env("BEDROCK_HAIKU45_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"), "HAIKU45",
    ),
]
CLAUDE_FAST_FIELDS_EXTRA = env_json("CLAUDE_FAST_FIELDS_EXTRA", {"thinking": {"type": "disabled"}})

OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", "https://api.openai.com")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-6-luna")
# gpt-6-luna accepts none / low / medium (default) / high / xhigh / max. "none" = answer directly.
OPENAI_REASONING_EFFORT = env("OPENAI_REASONING_EFFORT", "none")
OPENAI_MAX_TOKENS = env_int("OPENAI_MAX_TOKENS", 512)

CORS_ORIGINS = [o.strip() for o in (env("CORS_ORIGINS", "http://localhost:3000") or "").split(",") if o.strip()]
