# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==2.1.1", "psycopg[binary]==3.3.6"]
# ///
"""The agent's three tools as an MCP server, for LibreChat.

LibreChat starts this script itself (a stdio MCP server, configured in librechat.yaml) and
runs it with `uv run --script`, which installs the two dependencies declared above. It adds
nothing to the tools: names, parameters and docstrings come straight from agent/tools.py,
the same functions Strands uses.

    uv run --script agent/mcp_server.py      # what LibreChat runs
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Run as a script, so make `agent` importable from the directory above this file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer

from agent import tools

SERVER_NAME = "fda"
TOOL_FUNCTIONS = (tools.run_query, tools.create_plan, tools.complete_step)


def build_server() -> MCPServer:
    server = MCPServer(SERVER_NAME)
    for function in TOOL_FUNCTIONS:
        # The docstring without its indentation, and plain-text results, exactly as returned.
        server.add_tool(
            function, description=inspect.getdoc(function), structured_output=False
        )
    return server


if __name__ == "__main__":
    build_server().run("stdio")
