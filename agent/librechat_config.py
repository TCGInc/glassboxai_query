"""Write LibreChat's configuration from agent/, so both runtimes run the same agent.

start.sh runs it before starting LibreChat (rerun it, then restart LibreChat, after editing agent/):

    docker compose run --rm --no-deps jupyter python -m agent.librechat_config
    docker compose restart librechat

It writes librechat/librechat.yaml (generated, gitignored). There is no LibreChat agent object
to provision: a single model spec, "Glass Box FDA", carries the system prompt, the model and
reasoning effort, the three tools (agent/mcp_server.py, which LibreChat starts itself) and the
skills (agent/skills/, mounted as LibreChat's deployment skills). LibreChat builds the agent
from the spec on every chat.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from agent import settings
from agent.mcp_server import SERVER_NAME
from agent.strands_agent import SYSTEM_PROMPT_PATH

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "librechat" / "librechat.yaml"
CONFIG_VERSION = (
    "1.3.17"  # the librechat.yaml schema version LibreChat v0.8.8 ships with
)
SPEC_NAME = "glassbox-fda"
SPEC_LABEL = "Glass Box FDA"
MCP_SERVER_SCRIPT = (
    "/opt/glassbox/agent/mcp_server.py"  # ./agent is mounted at /opt/glassbox/agent
)
GEMINI_ENDPOINT = "Gemini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# Shown on a new chat. Each is the exact text of a benchmark question in tests/questions.yaml
# (q008, q029, q030, q017), so every demo prompt is regression-tested: three table-shaped
# questions, then one the data cannot answer.
CONVERSATION_STARTERS = [
    "For fiscal year 2024, how many recall events were there in each recall class?",
    "Please break down the number of recalls by product type for fiscal year 2025.",
    (
        "Which five states had the most inspections in fiscal year 2025, "
        "and how many inspections did each have?"
    ),
    "How many warning letters did the FDA issue to drug manufacturers in fiscal year 2025?",
]


def endpoint_for(model_id: str) -> str:
    """LibreChat endpoint that serves the model: OpenAI, or Gemini's OpenAI-compatible API."""
    return GEMINI_ENDPOINT if model_id.startswith("gemini") else "openAI"


def model_spec(model_id: str) -> dict:
    """The agent as a LibreChat model spec. Only the system prompt and reasoning effort are set."""
    effort = settings.reasoning_effort()
    return {
        "name": SPEC_NAME,
        "label": SPEC_LABEL,
        "description": "FDA inspections, citations and recalls, with the work shown.",
        "default": True,
        "showOnLanding": True,
        "conversation_starters": CONVERSATION_STARTERS,
        # The three tools and the skills. LibreChat's other tools (web search, code
        # execution, file search, memory) are off because the spec doesn't turn them on.
        "mcpServers": [SERVER_NAME],
        "skills": True,
        "preset": {
            "endpoint": endpoint_for(model_id),
            "model": model_id,
            "promptPrefix": SYSTEM_PROMPT_PATH.read_text(),
            **({"reasoning_effort": effort} if effort else {}),
        },
    }


def build_config(model_id: str, gemini_key: bool = False) -> dict:
    """The whole librechat.yaml. Gemini is offered when its key is set or the agent uses it."""
    endpoints = [endpoint_for(model_id)]
    if (
        gemini_key or model_id.startswith("gemini")
    ) and GEMINI_ENDPOINT not in endpoints:
        endpoints.append(GEMINI_ENDPOINT)
    config: dict = {
        "version": CONFIG_VERSION,
        "cache": True,
        "interface": {
            # The plain models stay selectable next to Glass Box FDA, so a demo can show what
            # the model does on its own. Hiding them is a customization for later.
            "modelSelect": True,
            "customWelcome": "Ask a question about FDA inspections, citations and recalls.",
            "skills": {"use": True, "create": False, "share": False, "public": False},
        },
        "endpoints": {
            "agents": {
                # No deferred tool search, code, web, files, memory or helper agents: the model
                # sees our three tools plus LibreChat's skill loader.
                "capabilities": ["tools", "skills"],
            },
        },
        "modelSpecs": {
            "enforce": False,
            "prioritize": True,
            "addedEndpoints": endpoints,
            "list": [model_spec(model_id)],
        },
        "mcpServers": {
            SERVER_NAME: {
                "type": "stdio",
                "command": "uv",
                "args": ["run", "--quiet", "--script", MCP_SERVER_SCRIPT],
                # Same read-only role as Strands. LibreChat substitutes the value from its own
                # environment when it starts the server.
                "env": {"FDA_DATABASE_URL": "${FDA_DATABASE_URL}"},
                # Reached through the Glass Box FDA spec, not offered as a chat toggle.
                "chatMenu": False,
                "timeout": 120000,
            },
        },
    }
    if GEMINI_ENDPOINT in endpoints:
        config["endpoints"]["custom"] = [
            {
                "name": GEMINI_ENDPOINT,
                "apiKey": "${GEMINI_API_KEY}",
                "baseURL": GEMINI_BASE_URL,
                "models": {
                    "default": [model_id] if endpoints[0] == GEMINI_ENDPOINT else [],
                    "fetch": True,
                },
                "titleConvo": True,
            }
        ]
    return config


class _Dumper(yaml.SafeDumper):
    """Writes multi-line strings (the system prompt) as readable YAML blocks."""


_Dumper.add_representer(
    str,
    lambda dumper, value: dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
    ),
)


def render(config: dict) -> str:
    header = (
        "# Generated by agent/librechat_config.py from agent/ and .env; do not edit here.\n"
        "# Rerun: docker compose run --rm --no-deps jupyter python -m agent.librechat_config\n"
    )
    return header + yaml.dump(
        config, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100
    )


def main() -> None:
    model_id = os.environ["LLM_MODEL_ID"]
    config = build_config(model_id, gemini_key=bool(os.environ.get("GEMINI_API_KEY")))
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(render(config))
    print(
        f"Wrote {OUTPUT_PATH.relative_to(OUTPUT_PATH.parent.parent)} ({SPEC_LABEL} on {model_id})"
    )


if __name__ == "__main__":
    main()
