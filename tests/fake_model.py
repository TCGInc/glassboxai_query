"""A scripted stand-in for the LLM, so agent wiring can be tested without tokens."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from strands.models import Model

# One scripted model turn: a final text answer, or tool calls as (name, input).
Turn = str | list[tuple[str, dict]]


class ScriptedModel(Model):
    """Replays `turns` in order and records what the agent sent on each call."""

    def __init__(self, turns: list[Turn]) -> None:
        self._turns = list(turns)
        self.system_prompts: list[str | None] = []
        self.tool_names: list[list[str]] = []

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> dict:
        return {}

    def structured_output(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict]:
        raise NotImplementedError

    async def stream(
        self, messages, tool_specs=None, system_prompt=None, **kwargs: Any
    ) -> AsyncIterator[dict]:
        self.system_prompts.append(system_prompt)
        self.tool_names.append([spec["name"] for spec in tool_specs or []])
        turn = self._turns.pop(0)

        yield {"messageStart": {"role": "assistant"}}
        if isinstance(turn, str):
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": turn}}}
            yield {"contentBlockStop": {}}
            stop_reason = "end_turn"
        else:
            for number, (name, tool_input) in enumerate(turn, start=1):
                tool_use = {
                    "toolUseId": f"call-{len(self.tool_names)}-{number}",
                    "name": name,
                }
                yield {"contentBlockStart": {"start": {"toolUse": tool_use}}}
                yield {
                    "contentBlockDelta": {
                        "delta": {"toolUse": {"input": json.dumps(tool_input)}}
                    }
                }
                yield {"contentBlockStop": {}}
            stop_reason = "tool_use"
        yield {"messageStop": {"stopReason": stop_reason}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
                "metrics": {"latencyMs": 0},
            }
        }
