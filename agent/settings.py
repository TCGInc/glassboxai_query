"""Model settings shared by both runtimes (read from the environment)."""

from __future__ import annotations

import os

DEFAULT_REASONING_EFFORT = "none"


def reasoning_effort() -> str | None:
    """Reasoning effort sent to OpenAI models; unset means "none", empty means provider default.

    "none" turns off hidden reasoning so the model reasons in visible text, which the
    Glass Box approach prefers. Temperature and other sampling settings stay at the
    provider defaults.
    """
    value = os.environ.get("LLM_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip()
    return value or None
