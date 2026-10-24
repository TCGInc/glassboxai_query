"""Re-grade a saved eval report with the current grading rules. Costs no tokens.

    python tests/regrade.py                       # latest report
    python tests/regrade.py tests/reports/X.json

Useful when tuning grading.py: the agent's answers and queries are in the report.
"""

import json
import sys
from pathlib import Path

import grading
from evalreport import REPORT_DIR, QuestionResult, RunRecord, render
from questions import gold_rows, load_questions

from agent.strands_agent import Answer, Query


def regrade(path: Path) -> list[QuestionResult]:
    questions = {q.id: q for q in load_questions()}
    results = []
    for saved in json.loads(path.read_text())["questions"]:
        q = questions[saved["id"]]
        gold = gold_rows(q.gold_sql) if q.gold_sql else None
        result = QuestionResult(id=q.id, tier=q.tier, question=q.question)
        signatures = []
        for run in saved["runs"]:
            if run["error"]:
                result.runs.append(
                    RunRecord(False, "error", "", [], error=run["error"])
                )
                signatures.append("error")
                continue
            queries = [Query(sql=x["sql"], result=x["result"]) for x in run["queries"]]
            answer = Answer(text=run["answer"], queries=queries)
            correct = grading.grade(q.expect, gold, q.ordered, answer)
            signature = (
                ("correct",)
                if correct
                else grading.signature(q.expect, q.ordered, answer)
            )
            signatures.append(signature)
            result.runs.append(
                RunRecord(correct, str(signature), run["answer"], run["queries"])
            )
        result.consistency = grading.consistency(signatures)
        results.append(result)
    return results


if __name__ == "__main__":
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else max(REPORT_DIR.glob("*.json"))
    print(f"Re-graded {report.name}\n")
    print("\n".join(render(regrade(report))))
