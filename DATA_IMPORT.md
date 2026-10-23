# Preparing the FDA CSV files

The source Excel workbooks belong in `data/raw/` with these canonical names:

```text
fda_inspections.xlsx
fda_citations.xlsx
fda_recall_events.xlsx
```

FDA downloads may have generated UUID filenames. After each download finishes, rename the file to its canonical name and place it in `data/raw/`. Keep the original workbook contents unchanged. The recall export has product-level rows and includes an `Event ID`; multiple product rows may refer to the same recall event.

Install the small local import dependency and run the conversion from the repository root:

```bash
python -m pip install -r requirements-import.txt
python scripts/convert_fda_workbooks.py
```

The script writes UTF-8 CSV snapshots to `data/` (`fda_inspections.csv`, `fda_citations.csv`, and `fda_recall_events.csv`) and records source/output hashes, row counts, worksheet names, and columns in `data/fda_import_manifest.json`. It validates the expected worksheet and headers before conversion, skips entirely blank rows, and stops if a downloaded export's schema changes. Use `--input-dir` or `--output-dir` to select alternate folders. These CSVs are intended for the later PostgreSQL load.

To refresh the snapshot, download all three current FDA workbooks, put them in `data/raw/` under the canonical names above, and rerun the command. Preserve the downloaded workbooks so a refresh can be reproduced and reviewed.
