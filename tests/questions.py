"""Load tests/questions.yaml and compute gold results from the database."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import yaml

QUESTIONS_PATH = Path(__file__).parent / "questions.yaml"


@dataclass(frozen=True)
class Question:
    id: str
    tier: str
    expect: str
    question: str
    notes: str
    gold_sql: str | None = None
    shape: dict = field(default_factory=dict)

    @property
    def ordered(self) -> bool:
        """Row order matters only when the gold query orders its result."""
        return bool(
            self.gold_sql and re.search(r"\border\s+by\b", self.gold_sql, re.IGNORECASE)
        )


def load_questions() -> list[Question]:
    return [Question(**item) for item in yaml.safe_load(QUESTIONS_PATH.read_text())]


def gold_rows(sql: str) -> list[list[str]]:
    """Run a gold query as agent_ro and return every row as strings."""
    with psycopg.connect(os.environ["FDA_DATABASE_URL"], autocommit=True) as conn:
        rows = conn.execute(sql).fetchall()
    return [["NULL" if value is None else str(value) for value in row] for row in rows]
