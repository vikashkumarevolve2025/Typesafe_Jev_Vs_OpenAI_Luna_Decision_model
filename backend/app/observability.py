"""Optional Langfuse tracing (SDK v3). Every helper is a no-op when keys are unset
or the SDK is missing, so the arena never fails because tracing is down."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

log = logging.getLogger("arena.langfuse")
_client: Any = None
_checked = False


def get_langfuse():
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import get_client

        _client = get_client()
    except Exception as exc:  # pragma: no cover - depends on env
        log.warning("Langfuse disabled: %s", exc)
        _client = None
    return _client


@contextlib.contextmanager
def span(name: str, *, input: Any = None, metadata: dict[str, Any] | None = None) -> Iterator[Any]:
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    try:
        cm = lf.start_as_current_span(name=name, input=input, metadata=metadata)
    except Exception as exc:  # pragma: no cover
        log.warning("Langfuse span failed: %s", exc)
        yield None
        return
    with cm as s:
        yield s


@contextlib.contextmanager
def generation(name: str, *, model: str | None, input: Any, metadata: dict[str, Any] | None = None) -> Iterator[Any]:
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    try:
        cm = lf.start_as_current_generation(name=name, model=model, input=input, metadata=metadata)
    except Exception as exc:  # pragma: no cover
        log.warning("Langfuse generation failed: %s", exc)
        yield None
        return
    with cm as g:
        yield g


def safe_update(obj: Any, **kwargs: Any) -> None:
    if obj is None:
        return
    try:
        obj.update(**{k: v for k, v in kwargs.items() if v is not None})
    except Exception as exc:  # pragma: no cover
        log.warning("Langfuse update failed: %s", exc)


def flush() -> None:
    lf = get_langfuse()
    if lf is not None:
        with contextlib.suppress(Exception):
            lf.flush()
