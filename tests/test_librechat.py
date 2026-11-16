"""Tier 1: the LibreChat configuration matches agent/ (the single source of truth).

The offline tests check what agent/librechat_config.py writes and what agent/mcp_server.py
exposes. The live tests ask a running LibreChat what it loaded, and skip when it is
unreachable (start the stack with ./start.sh).
"""

import asyncio
import inspect
import os
import urllib.request
from pathlib import Path

import pytest
import yaml

from agent import librechat_config as config
from agent import mcp_server, tools
from agent.strands_agent import SKILLS_DIR, SYSTEM_PROMPT_PATH

# --- offline ----------------------------------------------------------------


def test_mcp_server_exposes_exactly_the_agent_tools():
    listed = asyncio.run(mcp_server.build_server().list_tools())
    assert [t.name for t in listed] == [f.__name__ for f in mcp_server.TOOL_FUNCTIONS]
    for tool, function in zip(listed, mcp_server.TOOL_FUNCTIONS, strict=True):
        assert tool.description == inspect.getdoc(function)
        assert list(tool.input_schema["properties"]) == list(
            inspect.signature(function).parameters
        )


def test_mcp_server_delegates_to_agent_tools():
    server = mcp_server.build_server()

    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        return "".join(part.text for part in result.content)

    assert call("run_query", sql="SELECT 1 AS one") == tools.run_query(
        "SELECT 1 AS one"
    )
    assert call("run_query", sql="DROP TABLE x").startswith("Error:")
    assert call("create_plan", steps="A\nB") == "Plan:\n1. [pending] A\n2. [pending] B"
    assert call("complete_step", step=2, note="ok").endswith("2. [done] B (note: ok)")


def test_spec_carries_the_prompt_and_nothing_else_tunable():
    spec = config.model_spec("some-model")
    # No sampling settings: only the prompt and the shared reasoning effort.
    assert spec["preset"] == {
        "endpoint": "openAI",
        "model": "some-model",
        "promptPrefix": SYSTEM_PROMPT_PATH.read_text(),
        "reasoning_effort": "none",
    }
    assert spec["mcpServers"] == [mcp_server.SERVER_NAME]
    assert spec["skills"] is True
    # The one LibreChat tool we use: clarifying questions as a form with options.
    assert spec["askUserQuestion"] is True
    # LibreChat's other tools stay off: the spec doesn't turn any of them on.
    for flag in ("webSearch", "fileSearch", "executeCode", "memory"):
        assert flag not in spec


def test_gemini_models_use_the_gemini_endpoint():
    cfg = config.build_config("gemini-3-flash")
    assert cfg["modelSpecs"]["list"][0]["preset"]["endpoint"] == config.GEMINI_ENDPOINT
    assert cfg["endpoints"]["custom"][0]["name"] == config.GEMINI_ENDPOINT
    assert "custom" not in config.build_config("gpt-6-luna")["endpoints"]


def test_only_our_tools_skills_and_clarifying_questions_are_enabled():
    cfg = config.build_config("gpt-6-luna")
    assert cfg["endpoints"]["agents"]["capabilities"] == [
        "tools",
        "skills",
        "ask_user_question",
    ]
    server = cfg["mcpServers"][mcp_server.SERVER_NAME]
    assert server["type"] == "stdio" and server["args"][-1] == config.MCP_SERVER_SCRIPT
    assert server["env"] == {"FDA_DATABASE_URL": "${FDA_DATABASE_URL}"}


def test_rendered_yaml_round_trips():
    cfg = config.build_config("gpt-6-luna")
    assert yaml.safe_load(config.render(cfg)) == cfg


def test_conversation_starters_are_benchmark_questions():
    from questions import load_questions

    questions = {q.question for q in load_questions()}
    assert len(config.CONVERSATION_STARTERS) == 4
    for prompt in config.CONVERSATION_STARTERS:
        assert prompt in questions, "demo prompts should be regression-tested"


@pytest.mark.parametrize(
    "skill_dir", sorted(SKILLS_DIR.iterdir()), ids=lambda d: d.name
)
def test_skill_frontmatter_suits_librechat(skill_dir):
    text = (skill_dir / "SKILL.md").read_text()
    frontmatter = yaml.safe_load(
        text.split("---")[1]
    )  # LibreChat rejects invalid YAML here
    assert frontmatter["name"] == skill_dir.name
    # Longer descriptions are cut off in the skill list LibreChat shows the model.
    assert len(frontmatter["description"]) < 250


BRANDING_DIR = Path(__file__).resolve().parent.parent / "branding"
# What branding/apply.sh copies into LibreChat's client: source file -> URL path
BRANDING_FILES = {
    "logo.svg": "/assets/logo.svg",
    "icon.svg": config.SPEC_ICON_URL,
    "theme.css": "/assets/glassbox-theme.css",
}


def test_branding_files_are_where_apply_sh_copies_them():
    script = (BRANDING_DIR / "apply.sh").read_text()
    for name, url in BRANDING_FILES.items():
        assert (BRANDING_DIR / name).is_file()
        assert f'cp "$src/{name}" "$dist{url}"' in script
    # The agent's icon in the chat is the agency logo.
    assert config.model_spec("some-model")["iconURL"] == config.SPEC_ICON_URL


# --- live -------------------------------------------------------------------


@pytest.fixture(scope="module")
def librechat():
    # One login for the whole test session: LibreChat rate-limits logins.
    from librechat_runtime import _logged_in_client

    if not (os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD")):
        pytest.skip("LibreChat settings are not in the environment")
    try:
        return _logged_in_client()
    except Exception as error:  # noqa: BLE001 - unreachable or no admin yet: skip, don't fail
        pytest.skip(f"LibreChat not reachable: {error}")


def test_live_config_is_the_generated_one(librechat):
    # The file LibreChat mounts was written from the current agent/ and .env ...
    expected = config.build_config(
        os.environ["LLM_MODEL_ID"], gemini_key=bool(os.environ.get("GEMINI_API_KEY"))
    )
    assert yaml.safe_load(config.OUTPUT_PATH.read_text()) == expected, (
        "rerun agent.librechat_config, then restart LibreChat"
    )
    # ... and LibreChat serves that spec. It keeps the system prompt on the server.
    startup = librechat.request("GET", "/api/config")
    specs = {s["name"]: s for s in (startup.get("modelSpecs") or {}).get("list", [])}
    assert config.SPEC_NAME in specs, (
        "restart LibreChat after rerunning agent.librechat_config"
    )
    served = specs[config.SPEC_NAME]
    assert served["preset"]["model"] == os.environ["LLM_MODEL_ID"]
    assert served["conversation_starters"] == config.CONVERSATION_STARTERS
    assert "promptPrefix" not in served["preset"]


def test_live_tools_are_the_three_agent_tools(librechat):
    servers = librechat.request("GET", "/api/mcp/tools").get("servers", {})
    names = sorted(tool["name"] for tool in servers[mcp_server.SERVER_NAME]["tools"])
    assert names == sorted(f.__name__ for f in mcp_server.TOOL_FUNCTIONS)


def test_live_skills_are_the_skill_files(librechat):
    listed = librechat.request("GET", "/api/skills?limit=100")
    names = sorted(s["name"] for s in listed.get("skills", listed.get("data", [])))
    assert names == sorted(d.name for d in SKILLS_DIR.iterdir())


def test_live_branding_is_the_branding_files(librechat):
    # branding/apply.sh runs at LibreChat's start, so a stale copy means it needs a restart.
    def fetch(path: str) -> bytes:
        with urllib.request.urlopen(librechat.base_url + path, timeout=30) as response:
            return response.read()

    assert b'href="assets/glassbox-theme.css?v=' in fetch("/login")
    for name, url in BRANDING_FILES.items():
        assert fetch(url) == (BRANDING_DIR / name).read_bytes(), (
            "restart LibreChat to apply branding/"
        )
