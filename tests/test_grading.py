"""Tier 1: the grading rules, on canned agent answers."""

import pytest
from grading import (
    admits_unavailable,
    asks_clarification,
    consistency,
    grade,
    is_correct,
    parse_table,
    rows_match,
    signature,
    text_mentions,
)

from agent.strands_agent import Answer, Query


def answer(text="", *results):
    return Answer(text=text, queries=[Query(sql="SELECT", result=r) for r in results])


TABLE = "| name | n |\n|---|---|\n| Class I | 374 |\n| a\\|b | 1,590 |\n(2 rows)"


def test_parse_table():
    assert parse_table(TABLE) == [["Class I", "374"], ["a|b", "1,590"]]
    assert parse_table("| n |\n|---|\n(0 rows)") == []
    assert parse_table("Error: boom") is None
    assert parse_table("not a table") is None


def test_rows_match_ignores_order_unless_ordered():
    gold = [["A", "1"], ["B", "2"]]
    flipped = [["B", "2"], ["A", "1"]]
    assert rows_match(gold, flipped, ordered=False)
    assert not rows_match(gold, flipped, ordered=True)


def test_rows_match_tolerates_small_numeric_differences_and_formatting():
    assert rows_match([["28.9"]], [["28.90"]], ordered=False)
    assert rows_match([["15732"]], [["15,732"]], ordered=False)
    assert rows_match([["Class I"]], [[" class i "]], ordered=False)
    assert not rows_match([["15732"]], [["15733"]], ordered=False)


def test_rows_match_needs_the_same_rows_and_columns():
    assert not rows_match([["1"]], [["1"], ["1"]], ordered=False)
    assert not rows_match([["1", "x"]], [["1"]], ordered=False)
    assert not rows_match([["1"], ["1"]], [["1"], ["2"]], ordered=False)


@pytest.mark.parametrize(
    ("text", "row", "expected"),
    [
        ("There were 15,732 inspections.", ["15732"], True),
        ("About 28.9% had citations", ["28.9"], True),
        ("The answer is 21 CFR 1.502(a).", ["21 CFR 1.502(a)"], True),
        ("There were 15,000 inspections.", ["15732"], False),
        ("No idea", ["21 CFR 1.502(a)"], False),
    ],
)
def test_text_mentions(text, row, expected):
    assert text_mentions(text, row) is expected


def test_is_correct_by_last_successful_query():
    good = "| n |\n|---|\n| 388 |\n(1 row)"
    bad = "| n |\n|---|\n| 7 |\n(1 row)"
    assert is_correct([["388"]], False, answer("x", bad, good))
    # An error after a good query does not count as the last result.
    assert is_correct([["388"]], False, answer("x", good, "Error: nope"))
    assert not is_correct([["388"]], False, answer("x", good, bad))


def test_is_correct_falls_back_to_the_final_text():
    assert is_correct([["388"]], False, answer("There were 388 events."))
    assert is_correct([["388"], ["2"]], False, answer("388 and 2"))
    assert not is_correct([["388"], ["2"]], False, answer("Only 388."))


def test_asks_clarification():
    assert asks_clarification(answer("Do you mean fiscal or calendar 2025?"))
    assert not asks_clarification(answer("There were 5 inspections."))
    # A SQL answer that ends with a courtesy question is not a clarification.
    assert not asks_clarification(
        answer("Answer: 5.\nSELECT COUNT(*) FROM x\nAnything else?")
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The database does not contain warning letters.", True),
        ("Recall dates aren't recorded, so I can't determine that.", True),
        ("The data begins in fiscal year 2009, so 2005 is outside it.", True),
        ("There were 4,321 warning letters.", False),
    ],
)
def test_admits_unavailable(text, expected):
    assert admits_unavailable(answer(text)) is expected


def test_grade_dispatches_on_expectation():
    assert grade("clarify", None, False, answer("Which year?"))
    assert not grade("clarify", None, False, answer("It was 5."))
    assert grade(
        "unavailable", None, False, answer("That is not available in the data.")
    )
    assert grade("answer", [["5"]], False, answer("It was 5."))


def test_consistency_is_the_share_of_runs_in_the_majority():
    assert consistency(["a", "a", "a", "b"]) == 0.75
    assert consistency(["a"] * 5) == 1.0
    assert consistency([]) == 0.0


def test_signature_groups_equivalent_results():
    one = "| n | x |\n|---|---|\n| 1 | b |\n| 2 | a |\n(2 rows)"
    two = "| count | label |\n|---|---|\n| 2 | A |\n| 1 | B |\n(2 rows)"
    assert signature("answer", False, answer("", one)) == signature(
        "answer", False, answer("", two)
    )
    assert signature("answer", True, answer("", one)) != signature(
        "answer", True, answer("", two)
    )
    assert signature("answer", False, answer("no query")) == ("no-result",)


@pytest.mark.parametrize(
    "text",
    [
        "I can’t calculate the average from this dataset.",  # curly apostrophe
        "The database does **not** record hospitalization counts.",  # markdown bold
        "Inspection coverage begins in fiscal year 2009.",
        "Fiscal year 2005 is outside its coverage.",
    ],
)
def test_admits_unavailable_survives_typography_and_new_phrasings(text):
    assert admits_unavailable(answer(text))


def test_a_bare_zero_is_not_an_admission():
    assert not admits_unavailable(
        answer("There were 0 inspections in fiscal year 2005.")
    )


def test_clarification_survives_markdown():
    assert asks_clarification(answer("Do you mean **fiscal** or *calendar* 2025?"))


def test_multi_row_gold_can_be_matched_from_the_final_text():
    gold = [["Biologics", "8"], ["Devices", "87"]]
    text = "| Product type | n |\n|---|--:|\n| Biologics | 8 |\n| Devices | 87 |"
    # Its last query was only a check, so the text carries the answer.
    assert is_correct(gold, False, answer(text, "| s |\n|---|\n| 95 |\n(1 row)"))
    assert not is_correct(gold, False, answer("Biologics 8 and Devices 70"))
