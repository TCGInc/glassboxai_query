"""The agent on the AWS Strands runtime.

Everything that defines the agent lives in this package: the system prompt
(system_prompt.md), the two skills (skills/*/SKILL.md) and the three tools
(tools.py). This module only wires them into Strands. Model settings stay at
the provider defaults on purpose.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from strands import Agent, tool
from strands.models import Model
from strands.models.gemini import GeminiModel
from strands.models.openai import OpenAIModel
from strands.vended_plugins.skills import AgentSkills

from agent import tools

AGENT_DIR = Path(__file__).parent
SYSTEM_PROMPT_PATH = AGENT_DIR / "system_prompt.md"
SKILLS_DIR = AGENT_DIR / "skills"


@dataclass
class Query:
    """One run_query call and what it returned."""

    sql: str
    result: str

    @property
    def failed(self) -> bool:
        return self.result.startswith("Error:")


@dataclass
class Answer:
    """What the agent said, and the work it showed to get there."""

    text: str
    queries: list[Query] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)


def build_model(model_id: str | None = None) -> Model:
    """Create the LLM from LLM_MODEL_ID: Gemini ids use Gemini, everything else OpenAI."""
    model_id = model_id or os.environ["LLM_MODEL_ID"]
    if model_id.startswith("gemini"):
        return GeminiModel(
            client_args={"api_key": os.environ["GEMINI_API_KEY"]}, model_id=model_id
        )
    return OpenAIModel(
        client_args={"api_key": os.environ["OPENAI_API_KEY"]}, model_id=model_id
    )


def build_agent(model: Model | None = None) -> Agent:
    """A fresh agent with an empty conversation and an empty plan."""
    tools.reset_plan()
    return Agent(
        model=model or build_model(),
        system_prompt=SYSTEM_PROMPT_PATH.read_text(),
        tools=[
            tool(tools.run_query),
            tool(tools.create_plan),
            tool(tools.complete_step),
        ],
        plugins=[AgentSkills(skills=str(SKILLS_DIR))],
        callback_handler=None,
    )


def ask(agent: Agent, question: str) -> Answer:
    """Send a question and return the final text plus every query the agent ran."""
    before = len(agent.messages)
    result = agent(question)
    return Answer(text=str(result).strip(), **_trace(agent.messages[before:]))


def _trace(messages: list[dict]) -> dict:
    """Pair each run_query call with its result, in order, from the message log."""
    calls: dict[str, tuple[str, dict]] = {}
    results: dict[str, str] = {}
    order: list[str] = []
    for message in messages:
        for block in message["content"]:
            if "toolUse" in block:
                use = block["toolUse"]
                calls[use["toolUseId"]] = (use["name"], use["input"])
                order.append(use["toolUseId"])
            elif "toolResult" in block:
                result = block["toolResult"]
                results[result["toolUseId"]] = "\n".join(
                    part.get("text", "") for part in result["content"]
                )
    return {
        "tool_calls": [calls[i][0] for i in order],
        "queries": [
            Query(sql=calls[i][1].get("sql", ""), result=results.get(i, ""))
            for i in order
            if calls[i][0] == "run_query"
        ],
    }
