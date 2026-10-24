"""Measure what the skills contribute: run questions with and without them. Costs tokens.

    python tests/ablate.py q026 q027 q028            # 3 runs each, Strands runtime
    EVAL_RUNS=5 python tests/ablate.py q027

"Without" means an empty skills directory and no "read the skills" step in the system
prompt, so the agent proceeds with no domain guidance. (Leaving the step in makes the
agent refuse to answer, which is the right behavior for a missing skill but hides what
the skills' content is worth.) Run it from /workspace/tests inside the jupyter container.
"""

import os
import re
import sys
import tempfile
from pathlib import Path

import evalreport
from questions import load_questions

from agent import strands_agent
from agent.strands_agent import ask, build_agent


def without_skills() -> None:
    strands_agent.SKILLS_DIR = Path(tempfile.mkdtemp())
    prompt = re.sub(
        r"1\. Before writing any SQL.*?\n",
        "",
        strands_agent.SYSTEM_PROMPT_PATH.read_text(),
    )
    path = Path(tempfile.mkdtemp()) / "system_prompt.md"
    path.write_text(prompt)
    strands_agent.SYSTEM_PROMPT_PATH = path


def run(ids: list[str], runs: int) -> dict[str, float]:
    questions = [q for q in load_questions() if q.id in ids]
    scores = {}
    for q in questions:
        result = evalreport.evaluate(q, runs, lambda text: ask(build_agent(), text))
        scores[q.id] = result.correctness
    return scores


if __name__ == "__main__":
    ids, runs = sys.argv[1:], int(os.environ.get("EVAL_RUNS", "3"))
    with_skills = run(ids, runs)
    without_skills()
    without = run(ids, runs)
    print(f"{'id':<6}{'with skills':>12}{'without':>10}")
    for qid in ids:
        print(f"{qid:<6}{with_skills[qid]:>12.0%}{without[qid]:>10.0%}")
