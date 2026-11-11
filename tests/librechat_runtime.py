"""Run a question through LibreChat the way its chat UI does, for the parity benchmark.

It logs in as the demo admin, starts a chat on the Glass Box FDA model spec (the same request
the browser sends: the spec's preset plus its tools and skills), reads the response stream to
the end, and converts the finished message into the same Answer the Strands runner returns.
The chat is deleted afterwards so benchmark runs don't fill the admin's history.
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from pathlib import Path

import yaml

from agent.librechat_config import OUTPUT_PATH, SPEC_NAME
from agent.mcp_server import SERVER_NAME
from agent.strands_agent import Answer, Query

TIMEOUT_SECONDS = 300
NO_PARENT = "00000000-0000-0000-0000-000000000000"
# LibreChat accepts chat requests only from browsers; this names the client honestly.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 GlassBoxEval/1.0"
)
_MCP_SUFFIX = f"_mcp_{SERVER_NAME}"


def tool_name(name: str) -> str:
    """LibreChat names MCP tools `<tool>_mcp_<server>`; report them as agent/tools.py names them."""
    return name.removesuffix(_MCP_SUFFIX)


def answer_from_content(content: list[dict]) -> Answer:
    """Turn a LibreChat response message's content parts into an Answer."""
    answer = Answer(text="")
    texts = []
    for part in content:
        if part.get("type") == "tool_call":
            call = part["tool_call"]
            name = tool_name(call.get("name", ""))
            answer.tool_calls.append(name)
            if name == "run_query":
                args = call.get("args") or "{}"
                sql = (json.loads(args) if isinstance(args, str) else args).get(
                    "sql", ""
                )
                answer.queries.append(Query(sql=sql, result=call.get("output") or ""))
        elif part.get("type") == "text":
            texts = [
                part.get("text", "")
            ]  # the text after the last tool call is the answer
    answer.text = "\n".join(texts).strip()
    return answer


def answer_from_final(event: dict) -> Answer:
    """The Answer in the stream's final event; an empty one is an error with the raw event."""
    message = event.get("responseMessage") or {}
    answer = answer_from_content(message.get("content") or [])
    if not answer.text:
        raise RuntimeError(
            f"LibreChat returned an empty answer: {json.dumps(event)[:600]}"
        )
    return answer


class LibreChat:
    """The few LibreChat API calls the benchmark needs."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def open(self, method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        try:
            return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"{method} {path} -> {error.code}: {error.read().decode()[:300]}"
            ) from error

    def request(self, method: str, path: str, body: dict | None = None):
        with self.open(method, path, body) as response:
            raw = response.read()
        try:
            return json.loads(raw or "null")
        except ValueError:
            raise RuntimeError(f"{method} {path} returned {raw[:300]!r}") from None

    def log_in(self, email: str, password: str) -> None:
        self.token = self.request(
            "POST", "/api/auth/login", {"email": email, "password": password}
        )["token"]

    def final_event(self, stream_id: str) -> dict:
        """Read the server-sent events of a generation until its final one."""
        with self.open("GET", f"/api/agents/chat/stream/{stream_id}") as response:
            kind = ""
            for raw in response:
                line = raw.decode().rstrip("\n")
                if line.startswith("event:"):
                    kind = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:])
                    if kind == "error":
                        raise RuntimeError(f"LibreChat reported an error: {data}")
                    if data.get("final"):
                        return data
        raise RuntimeError("LibreChat's stream ended without a final message")


def chat_request(spec: dict, question: str) -> dict:
    """What the chat UI posts for a new chat on the spec.

    Only the spec's name, endpoint and model travel with the request; LibreChat adds the rest
    of the preset (the system prompt, reasoning effort) on the server, as it does for the browser.
    """
    return {
        "text": question,
        "sender": "User",
        "isCreatedByUser": True,
        "messageId": str(uuid.uuid4()),
        "parentMessageId": NO_PARENT,
        "conversationId": None,
        "endpoint": spec["preset"]["endpoint"],
        "model": spec["preset"]["model"],
        "spec": spec["name"],
        "ephemeralAgent": {"mcp": spec["mcpServers"], "skills": spec["skills"]},
    }


def load_spec(path: Path = OUTPUT_PATH) -> dict:
    """The Glass Box FDA spec from the generated librechat.yaml, exactly as LibreChat reads it."""
    specs = yaml.safe_load(path.read_text())["modelSpecs"]["list"]
    return next(spec for spec in specs if spec["name"] == SPEC_NAME)


_client: LibreChat | None = None


def _logged_in_client() -> LibreChat:
    global _client
    if _client is None:
        client = LibreChat(os.environ.get("LIBRECHAT_URL", "http://librechat:3080"))
        client.log_in(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
        _client = client
    return _client


def ask_librechat(question: str) -> Answer:
    client = _logged_in_client()
    spec = load_spec()
    started = client.request(
        "POST",
        f"/api/agents/chat/{spec['preset']['endpoint']}",
        chat_request(spec, question),
    )
    final = client.final_event(started["streamId"])
    conversation_id = (final.get("responseMessage") or {}).get("conversationId")
    if conversation_id:
        client.request(
            "DELETE", "/api/convos", {"arg": {"conversationId": conversation_id}}
        )
    return answer_from_final(final)
