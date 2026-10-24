"""Tier 1: the question file is well formed and every gold query runs."""

import re
from collections import Counter

import pytest
from questions import Question, gold_rows, load_questions

from agent.tools import MAX_ROWS

QUESTIONS = load_questions()
ANSWERABLE = [q for q in QUESTIONS if q.expect == "answer"]
EXPECT_FOR_TIER = {
    "easy": "answer",
    "medium": "answer",
    "hard": "answer",
    "ambiguous": "clarify",
    "unanswerable": "unavailable",
}


def test_ids_are_unique():
    counts = Counter(q.id for q in QUESTIONS)
    assert [i for i, n in counts.items() if n > 1] == []


def test_every_tier_is_represented():
    assert {q.tier for q in QUESTIONS} == set(EXPECT_FOR_TIER)


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q.id)
def test_question_is_consistent(q: Question):
    assert q.tier in EXPECT_FOR_TIER
    assert q.expect == EXPECT_FOR_TIER[q.tier]
    assert q.question.strip() and q.notes.strip()
    assert bool(q.gold_sql) == (q.expect == "answer"), (
        "gold_sql only for answerable questions"
    )


@pytest.mark.parametrize("q", ANSWERABLE, ids=lambda q: q.id)
def test_gold_sql_is_something_the_agent_could_run(q: Question):
    # run_query only accepts SELECT / WITH, so gold queries should too.
    assert re.match(r"\s*(select|with)\b", q.gold_sql, re.IGNORECASE)


@pytest.mark.parametrize("q", ANSWERABLE, ids=lambda q: q.id)
def test_gold_sql_runs_and_has_the_declared_shape(q: Question):
    rows = gold_rows(q.gold_sql)
    assert rows, "gold result is empty"
    assert len(rows) <= MAX_ROWS
    assert all(len(row) == q.shape["columns"] for row in rows)
    assert q.shape["min_rows"] <= len(rows) <= q.shape["max_rows"]
    assert all(cell != "NULL" for row in rows for cell in row)
