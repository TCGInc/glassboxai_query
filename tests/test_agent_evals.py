"""Tier 2: run the real agent on every question several times. Costs tokens.

    pytest -m agent                       # all questions, EVAL_RUNS runs each
    EVAL_QUESTIONS=q001,q014 pytest -m agent
    EVAL_TIERS=ambiguous,unanswerable pytest -m agent
    EVAL_RUNTIME=openwebui pytest -m agent    # same suite through Open WebUI (parity)

Settings: EVAL_RUNS (default 5), EVAL_MIN_CORRECT (default 0.8, the fraction of
runs that must be correct for a question to pass). Every run's final answer and
queries go to tests/reports/*.json for inspection.
"""

import os

import evalreport
import pytest
from openwebui_runtime import ask_openwebui
from questions import Question, load_questions

from agent.strands_agent import ask, build_agent

pytestmark = pytest.mark.agent

RUNS = int(os.environ.get("EVAL_RUNS", "5"))
MIN_CORRECT = float(os.environ.get("EVAL_MIN_CORRECT", "0.8"))
RUNTIME = os.environ.get("EVAL_RUNTIME", "strands")  # strands | openwebui
ONLY_IDS = set(filter(None, os.environ.get("EVAL_QUESTIONS", "").split(",")))
ONLY_TIERS = set(filter(None, os.environ.get("EVAL_TIERS", "").split(",")))

QUESTIONS = [
    q
    for q in load_questions()
    if (not ONLY_IDS or q.id in ONLY_IDS) and (not ONLY_TIERS or q.tier in ONLY_TIERS)
]


def _has_credentials() -> bool:
    model_id = os.environ.get("LLM_MODEL_ID", "")
    key = "GEMINI_API_KEY" if model_id.startswith("gemini") else "OPENAI_API_KEY"
    return bool(model_id and os.environ.get(key))


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q.id)
def test_question(q: Question):
    if not _has_credentials():
        pytest.skip("set LLM_MODEL_ID and OPENAI_API_KEY / GEMINI_API_KEY in .env")

    if RUNTIME == "openwebui":
        run_once = ask_openwebui
    else:

        def run_once(question):
            return ask(build_agent(), question)

    result = evalreport.evaluate(q, RUNS, run_once)
    evalreport.RESULTS.append(result)

    assert result.correctness >= MIN_CORRECT, (
        f"{q.id}: {result.correctness:.0%} of {RUNS} runs correct (need {MIN_CORRECT:.0%})"
    )
