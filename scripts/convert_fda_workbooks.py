#!/usr/bin/env python3
"""Convert the FDA Excel workbooks in data/raw/ to CSV files in data/."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_DIR = PROJECT_ROOT / "data"
WORKBOOK_NAMES = (
    "fda_inspections",
    "fda_citations",
    "fda_recall_events",
)


def csv_value(value: Any) -> str:
    """Convert Excel values to CSV text, keeping dates locale-independent."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def convert_workbook(name: str) -> int:
    source = RAW_DIR / f"{name}.xlsx"
    destination = DATA_DIR / f"{name}.csv"
    workbook = load_workbook(source, read_only=True, data_only=True)

    try:
        if len(workbook.worksheets) != 1:
            raise ValueError(
                f"{source.name}: expected one worksheet, found {len(workbook.worksheets)}"
            )

        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers or any(header is None or str(header).strip() == "" for header in headers):
            raise ValueError(f"{source.name}: first row must contain column headers")
        if len(set(headers)) != len(headers):
            raise ValueError(f"{source.name}: duplicate column headers")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        row_count = 0
        with destination.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(headers)
            for row in rows:
                if not any(value is not None and value != "" for value in row):
                    continue
                if len(row) != len(headers):
                    raise ValueError(f"{source.name}: data row has a different number of columns")
                writer.writerow(csv_value(value) for value in row)
                row_count += 1
    finally:
        workbook.close()

    return row_count


def main() -> None:
    for name in WORKBOOK_NAMES:
        rows = convert_workbook(name)
        print(f"{name}.xlsx -> {name}.csv ({rows:,} rows)")


if __name__ == "__main__":
    main()
