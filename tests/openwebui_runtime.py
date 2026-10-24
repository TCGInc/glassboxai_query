"""Run a question through Open WebUI the way its chat UI does, for the parity benchmark.

Open WebUI only executes tools server-side for requests that carry chat context (a saved
chat, a message id and a session id), so a bare API call would hand tool calls back to the
caller. This creates a chat, starts the completion, waits for the assistant message to
finish, and converts the saved record into the same Answer the Strands runner returns.
"""

from __future__ import annotations

import json
import os
import time
import uuid

from agent.openwebui_provision import MODEL_ID, TOOL_ID, OpenWebUI
from agent.strands_agent import Answer, Query

TIMEOUT_SECONDS = 300
POLL_SECONDS = 2


def answer_from_output(output: list[dict]) -> Answer:
    """Turn an Open WebUI assistant message's `output` items into an Answer."""
    results = {
        item["call_id"]: "\n".join(part.get("text", "") for part in item["output"])
        for item in output
        if item["type"] == "function_call_output"
    }
    answer = Answer(text="")
    for item in output:
        if item["type"] == "function_call":
            answer.tool_calls.append(item["name"])
            if item["name"] == "run_query":
                sql = json.loads(item.get("arguments") or "{}").get("sql", "")
                answer.queries.append(
                    Query(sql=sql, result=results.get(item["call_id"], ""))
                )
        elif item["type"] == "message":
            answer.text = "\n".join(
                part.get("text", "")
                for part in item["content"]
                if part.get("type") == "output_text"
            ).strip()
    return answer


def answer_from_message(message: dict) -> Answer:
    """The Answer in a finished assistant message; an empty one is an error with the raw record."""
    answer = answer_from_output(message.get("output") or [])
    if not answer.text:
        raise RuntimeError(
            f"Open WebUI returned an empty answer: {json.dumps(message)[:600]}"
        )
    return answer


_client: OpenWebUI | None = None


def _signed_in_client() -> OpenWebUI:
    global _client
    if _client is None:
        client = OpenWebUI(os.environ.get("OPENWEBUI_URL", "http://openwebui:8080"))
        client.sign_in(
            os.environ["WEBUI_ADMIN_EMAIL"], os.environ["WEBUI_ADMIN_PASSWORD"]
        )
        _client = client
    return _client


def ask_openwebui(question: str) -> Answer:
    client = _signed_in_client()
    user_id, assistant_id, now = str(uuid.uuid4()), str(uuid.uuid4()), int(time.time())
    user = {
        "id": user_id,
        "parentId": None,
        "childrenIds": [assistant_id],
        "role": "user",
        "content": question,
        "timestamp": now,
        "models": [MODEL_ID],
    }
    assistant = {
        "id": assistant_id,
        "parentId": user_id,
        "childrenIds": [],
        "role": "assistant",
        "content": "",
        "model": MODEL_ID,
        "timestamp": now,
        "done": False,
    }
    chat = client.request(
        "POST",
        "/api/v1/chats/new",
        {
            "chat": {
                "title": "benchmark",
                "models": [MODEL_ID],
                "messages": [user, assistant],
                "history": {
                    "messages": {user_id: user, assistant_id: assistant},
                    "currentId": assistant_id,
                },
            }
        },
    )
    chat_id = chat["id"]
    try:
        client.request(
            "POST",
            "/api/chat/completions",
            {
                "model": MODEL_ID,
                "stream": True,
                "tool_ids": [TOOL_ID],
                "messages": [{"role": "user", "content": question}],
                "chat_id": chat_id,
                "id": assistant_id,
                "parent_id": user_id,
                "session_id": str(uuid.uuid4()),
                "background_tasks": {},
            },
        )
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            saved = client.request("GET", f"/api/v1/chats/{chat_id}")
            message = saved["chat"]["history"]["messages"][assistant_id]
            if message.get("error"):
                raise RuntimeError(f"Open WebUI reported an error: {message['error']}")
            if message.get("done"):
                return answer_from_message(message)
            time.sleep(POLL_SECONDS)
        raise TimeoutError(f"Open WebUI did not finish within {TIMEOUT_SECONDS}s")
    finally:
        client.request("DELETE", f"/api/v1/chats/{chat_id}")
