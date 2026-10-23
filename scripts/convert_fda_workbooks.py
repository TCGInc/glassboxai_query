#!/usr/bin/env python3
"""Convert the project's FDA Excel source files to stable UTF-8 CSV snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data"
SHEET_NAME = "Sheet1"

# These headers identify the current FDA exports. A changed export should fail
# loudly so that schema changes are reviewed instead of silently discarded.
SOURCES: dict[str, tuple[str, ...]] = {
    "fda_inspections": (
        "FEI Number",
        "Legal Name",
        "City",
        "State",
        "Zip",
        "Country/Area",
        "Fiscal Year",
        "Inspection ID",
        "Posted Citations",
        "Inspection End Date",
        "Classification",
        "Project Area",
        "Product Type",
        "Additional Details",
        "FMD-145 Date",
    ),
    "fda_citations": (
        "Inspection ID",
        "FEI Number",
        "Legal Name",
        "Inspection End Date",
        "Program Area",
        "Act/CFR Number",
        "Short Description",
        "Long Description",
    ),
    "fda_recall_events": (
        "FEI Number",
        "Recalling Firm Name",
        "Product Type",
        "Product Classification",
        "Status",
        "Distribution Pattern",
        "Recalling Firm City",
        "Recalling Firm State",
        "Recalling Firm Country",
        "Center Classification Date",
        "Reason for Recall",
        "Product Description",
        "Event ID",
        "Event Classification",
        "Product ID",
        "Center",
        "Recall Details",
    ),
}


def _cell_to_csv(value: Any) -> str:
    """Serialize Excel values without locale-dependent formatting."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_headers(source_path: Path, expected_headers: Sequence[str]) -> None:
    workbook = load_workbook(source_path, read_only=True, data_only=True)
    try:
        if SHEET_NAME not in workbook.sheetnames:
            raise ValueError(
                f"{source_path.name}: expected worksheet {SHEET_NAME!r}; "
                f"found {workbook.sheetnames!r}"
            )
        worksheet = workbook[SHEET_NAME]
        actual_headers = tuple(next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True)))
        while actual_headers and actual_headers[-1] is None:
            actual_headers = actual_headers[:-1]
        if actual_headers != tuple(expected_headers):
            raise ValueError(
                f"{source_path.name}: column headers differ from the reviewed FDA export.\n"
                f"Expected: {tuple(expected_headers)!r}\n"
                f"Found:    {actual_headers!r}"
            )
        if len(set(actual_headers)) != len(actual_headers):
            raise ValueError(f"{source_path.name}: duplicate column headers found")
    finally:
        workbook.close()


def _write_csv(source_path: Path, output_path: Path, headers: Sequence[str]) -> int:
    workbook = load_workbook(source_path, read_only=True, data_only=True)
    temporary_path: Path | None = None
    try:
        worksheet = workbook[SHEET_NAME]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            writer = csv.writer(output_file, lineterminator="\n")
            writer.writerow(headers)
            row_count = 0
            for row in worksheet.iter_rows(min_row=2, values_only=True):
                values = tuple(row[: len(headers)])
                if len(values) < len(headers):
                    values += (None,) * (len(headers) - len(values))
                if not any(value is not None and value != "" for value in values):
                    continue
                if len(row) > len(headers) and any(value is not None for value in row[len(headers) :]):
                    raise ValueError(
                        f"{source_path.name}: data found beyond the reviewed header columns"
                    )
                writer.writerow(_cell_to_csv(value) for value in values)
                row_count += 1
        os.replace(temporary_path, output_path)
        temporary_path = None
        return row_count
    finally:
        workbook.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def convert(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Validate all source workbooks, convert them, and write a provenance manifest."""
    source_paths = {name: input_dir / f"{name}.xlsx" for name in SOURCES}
    missing = [path for path in source_paths.values() if not path.is_file()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Required FDA source workbook(s) not found: {names}")

    # Validate every workbook before replacing any existing CSV snapshot.
    for name, source_path in source_paths.items():
        _read_headers(source_path, SOURCES[name])

    manifest: dict[str, Any] = {
        "format_version": 1,
        "sources": {},
    }
    for name, source_path in source_paths.items():
        output_path = output_dir / f"{name}.csv"
        row_count = _write_csv(source_path, output_path, SOURCES[name])
        manifest["sources"][name] = {
            "source_file": source_path.name,
            "source_sha256": _sha256(source_path),
            "csv_file": output_path.name,
            "csv_sha256": _sha256(output_path),
            "sheet": SHEET_NAME,
            "row_count": row_count,
            "columns": list(SOURCES[name]),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "fda_import_manifest.json"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output_dir,
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as manifest_file:
        temporary_manifest = Path(manifest_file.name)
        json.dump(manifest, manifest_file, indent=2)
        manifest_file.write("\n")
    try:
        os.replace(temporary_manifest, manifest_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the three reviewed FDA Excel exports to CSV snapshots."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = convert(args.input_dir, args.output_dir)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        print(f"FDA workbook conversion failed: {error}", file=sys.stderr)
        return 1

    for name, details in manifest["sources"].items():
        print(f"{details['source_file']} -> {details['csv_file']}: {details['row_count']:,} rows")
    print(f"Wrote manifest: {args.output_dir / 'fda_import_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
