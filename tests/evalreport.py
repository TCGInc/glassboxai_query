"""Collects Tier 2 results and renders the summary table and JSON report."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import grading
from questions import Question, gold_rows

from agent.strands_agent import Answer

REPORT_DIR = Path(__file__).parent / "reports"


@dataclass
class RunRecord:
    correct: bool
    signature: str
    answer: str
    queries: list[dict]
    error: str = ""


@dataclass
class QuestionResult:
    id: str
    tier: str
    question: str
    runs: list[RunRecord] = field(default_factory=list)
    consistency: float = 0.0

    @property
    def correctness(self) -> float:
        return sum(r.correct for r in self.runs) / len(self.runs) if self.runs else 0.0


RESULTS: list[QuestionResult] = []


def render(results: list[QuestionResult]) -> list[str]:
    lines = [
        f"{'id':<6}{'tier':<13}{'runs':>5}{'correct':>9}{'consistent':>12}  question",
    ]
    for r in results:
        lines.append(
            f"{r.id:<6}{r.tier:<13}{len(r.runs):>5}{r.correctness:>9.0%}"
            f"{r.consistency:>12.0%}  {r.question[:60]}"
        )
    tiers = sorted({r.tier for r in results})
    lines.append("")
    for tier in [*tiers, None]:
        chosen = [r for r in results if tier in (None, r.tier)]
        correct = sum(r.correctness for r in chosen) / len(chosen)
        consistent = sum(r.consistency for r in chosen) / len(chosen)
        lines.append(
            f"{tier or 'ALL':<13} correctness {correct:>4.0%}  consistency {consistent:>4.0%}"
            f"  ({len(chosen)} questions)"
        )
    return lines


def write_report(results: list[QuestionResult], model_id: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    payload = {
        "model": model_id,
        "questions": [{**asdict(r), "correctness": r.correctness} for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def evaluate(
    q: Question, runs: int, run_once: Callable[[str], Answer]
) -> QuestionResult:
    """Ask `q` `runs` times and grade each run against the gold result or behavior."""
    gold = gold_rows(q.gold_sql) if q.gold_sql else None
    result = QuestionResult(id=q.id, tier=q.tier, question=q.question)
    signatures = []
    for _ in range(runs):
        try:
            answer = run_once(q.question)
        except Exception as error:  # noqa: BLE001 - an API hiccup costs one run, not the suite
            result.runs.append(RunRecord(False, "error", "", [], error=repr(error)))
            signatures.append("error")
            continue
        signature = grading.signature(q.expect, q.ordered, answer)
        signatures.append(signature)
        result.runs.append(
            RunRecord(
                correct=grading.grade(q.expect, gold, q.ordered, answer),
                signature=str(signature),
                answer=answer.text,
                queries=[{"sql": x.sql, "result": x.result} for x in answer.queries],
            )
        )
    result.consistency = grading.consistency(signatures)
    return result
