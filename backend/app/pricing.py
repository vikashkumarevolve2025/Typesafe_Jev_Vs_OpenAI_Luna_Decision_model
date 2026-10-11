"""Per-model token prices (USD per 1M tokens), read from env so nothing is hard-coded.

Unset prices return cost=None, which the UI shows as "price unknown".
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config
from .config import env_float


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


def _load(prefix: str) -> Price | None:
    pin, pout = env_float(f"PRICE_{prefix}_IN"), env_float(f"PRICE_{prefix}_OUT")
    if pin is None or pout is None:
        return None
    # Anthropic-style defaults when cache prices are not given: reads 0.1x, writes 1.25x input.
    cr = env_float(f"PRICE_{prefix}_CACHE_READ")
    cw = env_float(f"PRICE_{prefix}_CACHE_WRITE")
    return Price(pin, pout, cr if cr is not None else pin * 0.1, cw if cw is not None else pin * 1.25)


PRICES: dict[str, Price | None] = {
    key: _load(key) for key in ("OPUS", "SONNET", "JEV", "OPENAI", *(m[3] for m in config.CLAUDE_EXTRA_MODELS))
}


def cost_usd(price_key: str, usage: dict[str, int]) -> float | None:
    price = PRICES.get(price_key)
    if price is None:
        return None
    return (
        usage.get("input_tokens", 0) * price.input
        + usage.get("output_tokens", 0) * price.output
        + usage.get("cache_read_tokens", 0) * price.cache_read
        + usage.get("cache_write_tokens", 0) * price.cache_write
    ) / 1_000_000


def has_price(price_key: str) -> bool:
    return PRICES.get(price_key) is not None
