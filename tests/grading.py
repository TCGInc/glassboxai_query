"""Grading rules for the agent evals. Pure functions, unit tested without an LLM.

Answerable questions are graded on the result, not the SQL text: the agent is
correct when its last successful query returns the gold result set, or, for a
single-row gold result, when its final text states the gold values.

Clarification and "the data cannot answer this" are recognised with simple text
rules. They are provisional: an LLM judge would be more robust but costs tokens
and adds its own variance.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Hashable
from decimal import Decimal, InvalidOperation

from agent.strands_agent import Answer

TOLERANCE = Decimal("0.05")

_ADMISSIONS = [
    r"\b(?:not|n't) (?:available|included|contained|tracked|covered|recorded)\b",
    r"\bdoes(?: not|n't) (?:contain|include|cover|track|have|record|provide)\b",
    r"\bdo(?: not|n't) (?:contain|include|cover|track|have|provide)\b",
    r"\b(?:cannot|can't|can not|unable to) (?:answer|be answered|determine|provide|tell|calculate|compute)\b",
    r"\bno (?:data|information|records?)\b",
    r"\b(?:not|isn't|aren't) (?:in|part of) (?:the|this) (?:data|database|dataset)\b",
    r"\b(?:data|dataset|database) (?:begins|starts|only covers|only contains|ends)\b",
    r"\bcoverage (?:begins|starts|ends)\b",
    r"\boutside (?:of )?(?:its|the|this) (?:coverage|data|dataset|database|range)\b",
    r"\bcontains? no \w+ for\b",
]


def plain(text: str) -> str:
    """Text with curly quotes straightened and markdown emphasis removed, for matching."""
    table = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})
    return text.translate(table).replace("*", "").replace("`", "")


def parse_table(result: str) -> list[list[str]] | None:
    """Data rows of a run_query result as strings, or None for errors and non-tables."""
    if result.startswith("Error:"):
        return None
    lines = [line for line in result.splitlines() if line.startswith("|")]
    if len(lines) < 2:
        return None
    return [_split_row(line) for line in lines[2:]]


def _split_row(line: str) -> list[str]:
    cells = re.split(r"(?<!\\)\|", line)[1:-1]
    return [cell.strip().replace("\\|", "|") for cell in cells]


def _number(value: str) -> Decimal | None:
    try:
        number = Decimal(value.strip().replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def cells_equal(a: str, b: str) -> bool:
    """Numbers match within a small tolerance, text ignoring case and padding."""
    number_a, number_b = _number(a), _number(b)
    if number_a is not None and number_b is not None:
        return abs(number_a - number_b) <= TOLERANCE
    return a.strip().casefold() == b.strip().casefold()


def _rows_equal(a: list[str], b: list[str]) -> bool:
    return len(a) == len(b) and all(
        cells_equal(x, y) for x, y in zip(a, b, strict=True)
    )


def rows_match(gold: list[list[str]], got: list[list[str]], ordered: bool) -> bool:
    """Same rows, ignoring column names; ignoring row order unless `ordered`."""
    if len(gold) != len(got):
        return False
    if ordered:
        return all(_rows_equal(g, r) for g, r in zip(gold, got, strict=True))
    unused = list(got)
    for gold_row in gold:
        match = next((row for row in unused if _rows_equal(gold_row, row)), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def text_mentions(text: str, row: list[str]) -> bool:
    """Whether every value of a result row appears in the text (numbers by value)."""
    haystack = re.sub(r"(?<=\d),(?=\d{3}\b)", "", plain(text)).casefold()
    numbers = [Decimal(token) for token in re.findall(r"\d+(?:\.\d+)?", haystack)]
    for cell in row:
        value = _number(cell)
        if value is not None:
            if not any(abs(value - number) <= TOLERANCE for number in numbers):
                return False
        elif cell.strip().casefold() not in haystack:
            return False
    return True


def last_table(answer: Answer) -> list[list[str]] | None:
    tables = [t for q in answer.queries if (t := parse_table(q.result)) is not None]
    return tables[-1] if tables else None


def is_correct(gold: list[list[str]], ordered: bool, answer: Answer) -> bool:
    table = last_table(answer)
    if table is not None and rows_match(gold, table, ordered):
        return True
    return all(text_mentions(answer.text, row) for row in gold)


def asks_clarification(answer: Answer) -> bool:
    """A question back to the user, without a SQL answer."""
    text = plain(answer.text)
    return "?" in text and not re.search(r"\bselect\b", text, re.IGNORECASE)


def admits_unavailable(answer: Answer) -> bool:
    text = plain(answer.text)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in _ADMISSIONS)


def grade(
    expect: str, gold: list[list[str]] | None, ordered: bool, answer: Answer
) -> bool:
    if expect == "clarify":
        return asks_clarification(answer)
    if expect == "unavailable":
        return admits_unavailable(answer)
    assert gold is not None
    return is_correct(gold, ordered, answer)


def signature(expect: str, ordered: bool, answer: Answer) -> Hashable:
    """What a run amounts to, so runs can be compared with each other."""
    if expect == "clarify":
        return ("clarified", asks_clarification(answer))
    if expect == "unavailable":
        return ("declined", admits_unavailable(answer))
    table = last_table(answer)
    if table is None:
        return ("no-result",)
    rows = [tuple(_canonical(cell) for cell in row) for row in table]
    return ("rows", tuple(rows if ordered else sorted(rows)))


def _canonical(cell: str) -> str:
    number = _number(cell)
    return f"{number:.1f}" if number is not None else cell.strip().casefold()


def consistency(signatures: list[Hashable]) -> float:
    """Fraction of runs that agree with the most common outcome."""
    if not signatures:
        return 0.0
    return Counter(signatures).most_common(1)[0][1] / len(signatures)
