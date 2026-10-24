"""Tier 1: converting Open WebUI's saved message into an Answer (canned data, no LLM)."""

import json

import pytest
from openwebui_runtime import answer_from_message, answer_from_output

OUTPUT = [
    {
        "type": "function_call",
        "call_id": "c1",
        "name": "create_plan",
        "arguments": json.dumps({"steps": "Count"}),
        "status": "completed",
    },
    {
        "type": "function_call_output",
        "call_id": "c1",
        "output": [{"type": "input_text", "text": "Plan:\n1. [pending] Count"}],
    },
    {
        "type": "function_call",
        "call_id": "c2",
        "name": "run_query",
        "arguments": json.dumps({"sql": "SELECT COUNT(*) FROM recall_events"}),
        "status": "completed",
    },
    {
        "type": "function_call_output",
        "call_id": "c2",
        "output": [
            {"type": "input_text", "text": "| count |\n|---|\n| 37891 |\n(1 row)"}
        ],
    },
    {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "There are 37,891 events."}],
    },
]


def test_answer_from_output_pairs_calls_with_results():
    answer = answer_from_output(OUTPUT)
    assert answer.text == "There are 37,891 events."
    assert answer.tool_calls == ["create_plan", "run_query"]
    assert [q.sql for q in answer.queries] == ["SELECT COUNT(*) FROM recall_events"]
    assert "| 37891 |" in answer.queries[0].result and not answer.queries[0].failed


def test_answer_without_tool_calls():
    answer = answer_from_output([OUTPUT[-1]])
    assert answer.text and answer.queries == [] and answer.tool_calls == []


def test_an_empty_answer_is_an_error_that_keeps_the_raw_message():
    with pytest.raises(RuntimeError, match="empty answer.*abc"):
        answer_from_message({"id": "abc", "done": True, "output": []})
    assert answer_from_message({"output": OUTPUT}).text == "There are 37,891 events."
