"""The agent's three tools: run_query, create_plan, complete_step.

Plain functions with docstrings, independent of any agent framework. Each
runtime wraps them (Strands `@tool`, an Open WebUI Tools class) without
changing their behavior. The docstrings are what the model sees.

Tools return error text instead of raising, so the model can read the problem
and correct itself.
"""

from __future__ import annotations

import os
import re

import psycopg

MAX_ROWS = 50
MAX_CELL_CHARS = 200

_SELECT_ONLY = re.compile(r"(select|with)\b", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
_LIST_MARKER = re.compile(r"(?:\d+[.)]|[-*•])\s+")

# Each new plan replaces the previous one.
_plan: list[dict] = []


def run_query(sql: str) -> str:
    """Run one read-only SQL SELECT query against the FDA database and return the rows.

    Only a single SELECT (or WITH ... SELECT) statement is allowed. At most 50 rows
    are returned and long text values are cut off, so aggregate or filter in SQL
    rather than pulling raw rows. Use information_schema to discover tables and
    columns. Errors are returned as text so you can fix the query and retry.
    """
    statement = sql.strip().rstrip(";").rstrip()
    without_literals = _STRING_LITERAL.sub("''", statement)
    if not _SELECT_ONLY.match(statement) or ";" in without_literals:
        return "Error: only a single SELECT query is allowed."

    try:
        with (
            psycopg.connect(os.environ["FDA_DATABASE_URL"], autocommit=True) as conn,
            conn.cursor() as cur,
        ):
            cur.execute(statement)
            if cur.description is None:
                return "Error: the statement did not return rows."
            columns = [column.name for column in cur.description]
            rows = cur.fetchmany(MAX_ROWS + 1)
    except psycopg.Error as error:
        return f"Error: {str(error).strip()}"

    return _format_rows(columns, rows)


def create_plan(steps: str) -> str:
    """Record a multi-step plan for answering the question, one step per line.

    Creating a new plan replaces any earlier plan. Returns the plan with numbered
    steps, their status, and notes.
    """
    lines = (_LIST_MARKER.sub("", line.strip(), count=1) for line in steps.splitlines())
    texts = [line for line in lines if line]
    if not texts:
        return "Error: the plan needs at least one step, one per line."
    _plan[:] = [{"text": text, "done": False, "note": ""} for text in texts]
    return _render_plan()


def complete_step(step: int, note: str = "") -> str:
    """Mark a plan step as done, with an optional note about the outcome.

    `step` is the step's number in the plan. Returns the updated plan.
    """
    if not _plan:
        return "Error: there is no plan yet. Call create_plan first."
    if not 1 <= step <= len(_plan):
        return f"Error: step must be between 1 and {len(_plan)}.\n{_render_plan()}"
    _plan[step - 1].update(done=True, note=note.strip())
    return _render_plan()


def _format_rows(columns: list[str], rows: list[tuple]) -> str:
    shown = rows[:MAX_ROWS]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
        *(
            "| " + " | ".join(_format_cell(value) for value in row) + " |"
            for row in shown
        ),
        f"({len(shown)} row{'s' if len(shown) != 1 else ''})",
    ]
    if len(rows) > MAX_ROWS:
        lines.append(
            f"Only the first {MAX_ROWS} rows are shown and more exist. "
            "Aggregate, filter, or order the query to get what you need."
        )
    return "\n".join(lines)


def _format_cell(value: object) -> str:
    if value is None:
        return "NULL"
    text = " ".join(str(value).split()).replace("|", "\\|")
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS] + "… [truncated]"
    return text


def _render_plan() -> str:
    lines = ["Plan:"]
    for number, item in enumerate(_plan, start=1):
        line = f"{number}. [{'done' if item['done'] else 'pending'}] {item['text']}"
        if item["note"]:
            line += f" (note: {item['note']})"
        lines.append(line)
    return "\n".join(lines)
