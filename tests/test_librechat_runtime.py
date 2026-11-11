"""Tier 1: converting LibreChat's finished message into an Answer (canned data, no LLM)."""

import json

import pytest
from librechat_runtime import (
    answer_from_content,
    answer_from_final,
    chat_request,
    tool_name,
)


def call(name, args, output):
    return {
        "type": "tool_call",
        "tool_call": {"name": name, "args": json.dumps(args), "output": output},
    }


CONTENT = [
    call("skill", {"skillName": "database"}, 'Skill "database" loaded.'),
    {"type": "text", "text": "Let me plan this."},
    call("create_plan_mcp_fda", {"steps": "Count"}, "Plan:\n1. [pending] Count"),
    call(
        "run_query_mcp_fda",
        {"sql": "SELECT COUNT(*) FROM recall_events"},
        "| count |\n|---|\n| 37891 |\n(1 row)",
    ),
    {"type": "text", "text": "There are 37,891 events."},
]


def test_answer_from_content_pairs_calls_with_results():
    answer = answer_from_content(CONTENT)
    assert answer.text == "There are 37,891 events."
    assert answer.tool_calls == ["skill", "create_plan", "run_query"]
    assert [q.sql for q in answer.queries] == ["SELECT COUNT(*) FROM recall_events"]
    assert "| 37891 |" in answer.queries[0].result and not answer.queries[0].failed


def test_tool_names_drop_the_mcp_server_suffix():
    assert tool_name("run_query_mcp_fda") == "run_query"
    assert tool_name("skill") == "skill"


def test_an_empty_answer_is_an_error_that_keeps_the_raw_event():
    with pytest.raises(RuntimeError, match="empty answer.*abc"):
        answer_from_final(
            {"final": True, "responseMessage": {"messageId": "abc", "content": []}}
        )
    final = {"final": True, "responseMessage": {"content": CONTENT}}
    assert answer_from_final(final).text == "There are 37,891 events."


def test_chat_request_names_the_spec_and_leaves_the_prompt_to_the_server():
    spec = {
        "name": "glassbox-fda",
        "mcpServers": ["fda"],
        "skills": True,
        "preset": {"endpoint": "openAI", "model": "m", "promptPrefix": "P"},
    }
    body = chat_request(spec, "How many?")
    assert body["text"] == "How many?" and body["spec"] == "glassbox-fda"
    assert body["endpoint"] == "openAI" and body["model"] == "m"
    assert "promptPrefix" not in body
    assert body["ephemeralAgent"] == {"mcp": ["fda"], "skills": True}
