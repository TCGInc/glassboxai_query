"""Tier 1: deterministic tool and database-role tests. Need the postgres container."""

import os

import psycopg
import pytest

from agent.tools import MAX_CELL_CHARS, MAX_ROWS, complete_step, create_plan, run_query

# --- run_query -------------------------------------------------------------


def test_run_query_returns_table():
    result = run_query("SELECT 1 AS one, 'a|b' AS text, NULL AS missing")
    assert result.splitlines() == [
        "| one | text | missing |",
        "|---|---|---|",
        "| 1 | a\\|b | NULL |",
        "(1 row)",
    ]


def test_run_query_reads_fda_tables_without_schema_prefix():
    assert "| 277312 |" in run_query("SELECT COUNT(*) FROM inspections")


def test_run_query_allows_with_and_trailing_semicolon():
    assert "| 3 |" in run_query("WITH t AS (SELECT 3 AS n) SELECT n FROM t;")


def test_run_query_allows_semicolon_inside_string_literal():
    assert "| a;b |" in run_query("SELECT 'a;b' AS s")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fda.inspections",
        "INSERT INTO fda.inspections SELECT * FROM fda.inspections",
        "DROP TABLE fda.inspections",
        "SELECT 1; DROP TABLE fda.inspections",
        "SELECT 1; SELECT 2",
        "  ",
        "",
    ],
)
def test_run_query_rejects_non_select(sql):
    assert run_query(sql) == "Error: only a single SELECT query is allowed."


def test_documented_limits():
    assert MAX_ROWS == 50  # AGENTS.md and README promise 50 rows


def test_run_query_caps_rows():
    result = run_query(f"SELECT n FROM generate_series(1, {MAX_ROWS + 25}) AS n")
    assert f"({MAX_ROWS} rows)" in result
    assert f"| {MAX_ROWS} |" in result
    assert f"| {MAX_ROWS + 1} |" not in result
    assert "more exist" in result


def test_run_query_exact_cap_is_not_flagged_as_truncated():
    result = run_query(f"SELECT n FROM generate_series(1, {MAX_ROWS}) AS n")
    assert f"({MAX_ROWS} rows)" in result
    assert "more exist" not in result


def test_run_query_truncates_long_cells():
    result = run_query(f"SELECT repeat('x', {MAX_CELL_CHARS * 3}) AS long_text")
    assert "x" * MAX_CELL_CHARS + "… [truncated]" in result
    assert "x" * (MAX_CELL_CHARS + 1) not in result


def test_run_query_returns_sql_errors_as_text():
    result = run_query("SELECT no_such_column FROM inspections")
    assert result.startswith("Error:")
    assert "no_such_column" in result


def test_regex_is_not_the_guardrail_the_database_role_is():
    # Passes the SELECT/WITH regex, so only the read-only role stops it.
    result = run_query(
        "WITH gone AS (DELETE FROM fda.recall_events RETURNING 1) SELECT COUNT(*) FROM gone"
    )
    assert result.startswith("Error:")
    assert "read-only" in result or "permission denied" in result
    assert "| 37891 |" in run_query("SELECT COUNT(*) FROM recall_events")


# --- agent_ro role ----------------------------------------------------------


def _connect():
    return psycopg.connect(os.environ["FDA_DATABASE_URL"], autocommit=True)


def test_role_settings():
    with _connect() as conn:
        settings = dict(
            conn.execute(
                "SELECT name, setting FROM pg_settings WHERE name IN "
                "('default_transaction_read_only', 'statement_timeout')"
            ).fetchall()
        )
    assert settings == {
        "default_transaction_read_only": "on",
        "statement_timeout": "30000",
    }


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fda.recall_events",
        "INSERT INTO fda.recall_events SELECT * FROM fda.recall_events",
        "UPDATE fda.recall_events SET status = 'x'",
        "CREATE TABLE fda.x (a int)",
        "CREATE TEMP TABLE t (a int)",
        "TRUNCATE fda.citations",
        "COPY fda.inspections TO PROGRAM 'id'",
        "SELECT pg_read_file('/etc/passwd')",
    ],
)
def test_role_cannot_write_or_reach_the_server(sql):
    with _connect() as conn, pytest.raises(psycopg.errors.Error):
        conn.execute(sql)


def test_role_cannot_write_even_after_switching_to_read_write():
    with _connect() as conn:
        conn.execute("SET default_transaction_read_only = off")
        with pytest.raises(psycopg.errors.Error):
            conn.execute("DELETE FROM fda.recall_events")


# --- create_plan / complete_step -------------------------------------------


def test_create_plan_renders_numbered_pending_steps():
    assert create_plan("Find the table\nCount the rows\n") == (
        "Plan:\n1. [pending] Find the table\n2. [pending] Count the rows"
    )


def test_create_plan_ignores_blank_lines_and_list_markers():
    result = create_plan(
        "1. First\n\n  2) Second\n- Third\n* Fourth\n1.5 million is a number"
    )
    assert result.splitlines() == [
        "Plan:",
        "1. [pending] First",
        "2. [pending] Second",
        "3. [pending] Third",
        "4. [pending] Fourth",
        "5. [pending] 1.5 million is a number",
    ]


def test_create_plan_requires_a_step():
    assert create_plan(" \n\n").startswith("Error:")


def test_new_plan_replaces_old_plan():
    create_plan("Old one\nOld two")
    complete_step(1, "done")
    assert create_plan("New one") == "Plan:\n1. [pending] New one"
    assert complete_step(2).startswith("Error:")


def test_complete_step_marks_done_with_note():
    create_plan("First\nSecond")
    assert complete_step(2, " found 12 rows ") == (
        "Plan:\n1. [pending] First\n2. [done] Second (note: found 12 rows)"
    )


def test_complete_step_without_note_and_out_of_order():
    create_plan("First\nSecond\nThird")
    result = complete_step(3)
    assert result.splitlines()[-1] == "3. [done] Third"
    assert "1. [pending] First" in result


def test_complete_step_can_be_repeated_to_update_the_note():
    create_plan("Only")
    complete_step(1, "first try")
    assert complete_step(1, "revised") == "Plan:\n1. [done] Only (note: revised)"


@pytest.mark.parametrize("step", [0, -1, 3])
def test_complete_step_rejects_bad_numbers(step):
    create_plan("First\nSecond")
    result = complete_step(step)
    assert result.startswith("Error: step must be between 1 and 2.")
    assert "[done]" not in result


def test_complete_step_without_a_plan():
    assert complete_step(1) == "Error: there is no plan yet. Call create_plan first."
