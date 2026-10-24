"""Tier 1: the Strands wiring, driven by a scripted model (no LLM, no tokens)."""

from fake_model import ScriptedModel

from agent.strands_agent import SKILLS_DIR, SYSTEM_PROMPT_PATH, ask, build_agent


def run(turns):
    model = ScriptedModel(turns)
    agent = build_agent(model)
    return model, agent


def test_agent_exposes_three_tools_plus_the_skill_loader():
    model, agent = run(["hello"])
    ask(agent, "hi")
    assert sorted(model.tool_names[0]) == [
        "complete_step",
        "create_plan",
        "run_query",
        "skills",
    ]


def test_system_prompt_and_skill_catalog_reach_the_model():
    model, agent = run(["hello"])
    ask(agent, "hi")
    prompt = model.system_prompts[0]
    assert SYSTEM_PROMPT_PATH.read_text().strip() in prompt
    for skill in sorted(path.name for path in SKILLS_DIR.iterdir()):
        assert f"<name>{skill}</name>" in prompt
    # Only names and descriptions are in the prompt until a skill is loaded.
    assert "Fiscal year (FY)" not in prompt


def test_loading_a_skill_returns_its_full_text():
    _, agent = run(
        [[("skills", {"skill_name": "terminology"})], "done"],
    )
    answer = ask(agent, "What is OAI?")
    assert answer.tool_calls == ["skills"]
    skill_result = next(
        block["toolResult"]
        for message in agent.messages
        for block in message["content"]
        if "toolResult" in block
    )
    assert "Official Action Indicated (OAI)" in skill_result["content"][0]["text"]


def test_ask_traces_queries_results_and_final_text():
    _, agent = run(
        [
            [("run_query", {"sql": "SELECT COUNT(*) AS n FROM recall_events"})],
            [("run_query", {"sql": "SELECT nope FROM recall_events"})],
            "There are 37,891 recall events.",
        ]
    )
    answer = ask(agent, "How many recall events?")
    assert answer.text == "There are 37,891 recall events."
    assert answer.tool_calls == ["run_query", "run_query"]
    first, second = answer.queries
    assert "| 37891 |" in first.result and not first.failed
    assert second.failed


def test_plan_tools_work_through_the_agent():
    _, agent = run(
        [
            [("create_plan", {"steps": "Look up tables\nCount rows"})],
            [("complete_step", {"step": 1, "note": "found"})],
            "ok",
        ]
    )
    ask(agent, "plan something")
    results = [
        block["toolResult"]["content"][0]["text"]
        for message in agent.messages
        for block in message["content"]
        if "toolResult" in block
    ]
    assert (
        results[-1]
        == "Plan:\n1. [done] Look up tables (note: found)\n2. [pending] Count rows"
    )


def test_each_built_agent_starts_without_a_plan():
    _, agent = run([[("create_plan", {"steps": "One"})], "ok"])
    ask(agent, "plan")
    _, second = run([[("complete_step", {"step": 1})], "ok"])
    answer = ask(second, "complete")
    assert answer.tool_calls == ["complete_step"]
    result = next(
        block["toolResult"]["content"][0]["text"]
        for message in second.messages
        for block in message["content"]
        if "toolResult" in block
    )
    assert result.startswith("Error: there is no plan yet")
