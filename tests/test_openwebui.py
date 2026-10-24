"""Tier 1: the Open WebUI configuration matches agent/ (the single source of truth).

The offline tests check what the provisioner would send. The live tests compare
what a running Open WebUI actually stores, and skip when it is unreachable or not
provisioned yet (run `python -m agent.openwebui_provision`).
"""

import inspect
import os

import pytest

from agent import openwebui_provision as provision
from agent import tools
from agent.strands_agent import SKILLS_DIR, SYSTEM_PROMPT_PATH


def load_generated_tool():
    namespace: dict = {}
    exec(compile(provision.build_tool_content(), "<generated tool>", "exec"), namespace)  # noqa: S102
    return namespace["Tools"]()


# --- offline ----------------------------------------------------------------


def test_generated_tool_mirrors_agent_tools():
    generated = load_generated_tool()
    for function in provision.TOOL_FUNCTIONS:
        method = getattr(generated, function.__name__)
        assert list(inspect.signature(method).parameters) == list(
            inspect.signature(function).parameters
        )
        assert inspect.getdoc(method) == inspect.getdoc(function)
    assert [name for name in dir(generated) if not name.startswith("_")] == sorted(
        f.__name__ for f in provision.TOOL_FUNCTIONS
    )


def test_generated_tool_delegates_to_agent_tools():
    generated = load_generated_tool()
    assert generated.run_query("SELECT 1 AS one") == tools.run_query("SELECT 1 AS one")
    assert generated.run_query("DROP TABLE x").startswith("Error:")
    assert generated.create_plan("A\nB") == "Plan:\n1. [pending] A\n2. [pending] B"
    assert generated.complete_step(2, "ok").endswith("2. [done] B (note: ok)")


def test_skill_payloads_are_the_skill_files():
    payloads = provision.skill_payloads()
    assert [p["id"] for p in payloads] == sorted(d.name for d in SKILLS_DIR.iterdir())
    for payload in payloads:
        text = (SKILLS_DIR / payload["id"] / "SKILL.md").read_text()
        assert payload["content"] == text
        assert payload["description"] and payload["description"] in text


def test_model_payload_carries_the_prompt_and_nothing_else_tunable():
    payload = provision.model_payload("some-model", ["database", "terminology"])
    # No sampling settings: only the prompt and the shared reasoning effort.
    assert payload["params"] == {
        "system": SYSTEM_PROMPT_PATH.read_text(),
        "reasoning_effort": "none",
    }
    assert payload["base_model_id"] == "some-model"
    assert payload["meta"]["toolIds"] == [provision.TOOL_ID]
    assert payload["meta"]["skillIds"] == ["database", "terminology"]
    assert payload["meta"]["capabilities"] == {"builtin_tools": False}


def test_suggested_prompts_are_benchmark_questions():
    from questions import load_questions

    questions = {q.question for q in load_questions()}
    prompts = provision.SUGGESTED_PROMPTS
    assert len(prompts) == 3
    for prompt in prompts:
        assert prompt["content"] in questions, (
            "demo prompts should be regression-tested"
        )
        assert len(prompt["title"]) == 2 and all(prompt["title"])
    assert provision.model_payload("m", [])["meta"]["suggestion_prompts"] == prompts


# --- live -------------------------------------------------------------------


@pytest.fixture(scope="module")
def webui():
    url = os.environ.get("OPENWEBUI_URL", "")
    email = os.environ.get("WEBUI_ADMIN_EMAIL", "")
    password = os.environ.get("WEBUI_ADMIN_PASSWORD", "")
    if not (url and email and password):
        pytest.skip("Open WebUI settings are not in the environment")
    client = provision.OpenWebUI(url)
    try:
        client.sign_in(email, password)
    except Exception as error:  # noqa: BLE001 - unreachable or wrong credentials: skip, don't fail
        pytest.skip(f"Open WebUI not reachable: {error}")
    return client


def test_live_tool_matches_agent(webui):
    try:
        stored = webui.request("GET", f"/api/v1/tools/id/{provision.TOOL_ID}")
    except RuntimeError:
        pytest.skip("not provisioned yet")
    assert stored["content"] == provision.build_tool_content()
    assert sorted(spec["name"] for spec in stored["specs"]) == sorted(
        f.__name__ for f in provision.TOOL_FUNCTIONS
    )


def test_live_skills_match_agent(webui):
    for payload in provision.skill_payloads():
        try:
            stored = webui.request("GET", f"/api/v1/skills/id/{payload['id']}")
        except RuntimeError:
            pytest.skip("not provisioned yet")
        assert stored["content"] == payload["content"]
        assert stored["is_active"]


def test_live_model_matches_agent(webui):
    models = webui.request("GET", "/api/v1/models/list?query=&page=1")["items"]
    stored = next((m for m in models if m["id"] == provision.MODEL_ID), None)
    if stored is None:
        pytest.skip("not provisioned yet")
    expected = provision.model_payload(
        os.environ["LLM_MODEL_ID"], [p["id"] for p in provision.skill_payloads()]
    )
    assert stored["params"] == expected["params"]
    assert stored["base_model_id"] == expected["base_model_id"]
    for key, value in expected["meta"].items():
        assert stored["meta"][key] == value


def test_live_demo_settings(webui):
    config = webui.request("GET", "/api/v1/tasks/config")
    assert config["ENABLE_FOLLOW_UP_GENERATION"] is False
    assert provision.MODEL_ID in (
        webui.request("GET", "/api/config").get("default_models") or ""
    )


def test_live_model_picker_is_short_and_includes_the_base_model(webui):
    ids = [m["id"] for m in webui.request("GET", "/api/models")["data"]]
    assert provision.MODEL_ID in ids
    assert os.environ["LLM_MODEL_ID"] in ids, (
        "LLM_MODEL_ID must be in OPENAI_API_CONFIGS"
    )
    assert len(ids) <= 12, f"model picker should be short for demos, found {len(ids)}"
