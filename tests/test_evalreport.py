"""Tier 1: the Tier 2 harness itself, driven by scripted agents (no LLM)."""

import evalreport
from fake_model import ScriptedModel
from questions import load_questions

from agent.strands_agent import ask, build_agent

QUESTIONS = {q.id: q for q in load_questions()}


def runner(*scripts):
    """A run_once that plays one script per call; an Exception instance is raised."""
    pending = list(scripts)

    def run_once(question):
        script = pending.pop(0)
        if isinstance(script, Exception):
            raise script
        return ask(build_agent(ScriptedModel(script)), question)

    return run_once


QUERY_388 = [
    (
        "run_query",
        {
            "sql": "SELECT COUNT(*) FROM recall_events WHERE event_classification = 'Class I' AND center_classification_date BETWEEN '2024-10-01' AND '2025-09-30'"
        },
    )
]
QUERY_WRONG = [("run_query", {"sql": "SELECT 7"})]


def test_evaluate_scores_correctness_and_consistency_for_answers():
    result = evalreport.evaluate(
        QUESTIONS["q002"],
        4,
        runner(
            [QUERY_388, "388 events."],
            [QUERY_388, "There were 388."],
            [QUERY_WRONG, "7 events."],
            RuntimeError("api down"),
        ),
    )
    assert [r.correct for r in result.runs] == [True, True, False, False]
    assert result.runs[3].error.startswith("RuntimeError")
    assert result.correctness == 0.5
    assert (
        result.consistency == 0.5
    )  # two runs share the right result, the others differ


def test_evaluate_ambiguous_and_unanswerable_questions():
    ambiguous = evalreport.evaluate(
        QUESTIONS["q014"],
        2,
        runner(["Fiscal or calendar year, and which one?"], ["There were 5."]),
    )
    assert [r.correct for r in ambiguous.runs] == [True, False]
    unanswerable = evalreport.evaluate(
        QUESTIONS["q017"], 1, runner(["The database does not contain warning letters."])
    )
    assert unanswerable.correctness == 1.0


def test_render_and_report(tmp_path, monkeypatch):
    result = evalreport.evaluate(
        QUESTIONS["q017"], 2, runner(["Not available in the data."], ["It was 9."])
    )
    text = "\n".join(evalreport.render([result]))
    assert "q017" in text and "50%" in text and "ALL" in text
    monkeypatch.setattr(evalreport, "REPORT_DIR", tmp_path)
    path = evalreport.write_report([result], "test-model")
    assert "test-model" in path.read_text() and "Not available" in path.read_text()
