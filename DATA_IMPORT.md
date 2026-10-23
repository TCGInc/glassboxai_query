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

The script writes UTF-8 CSV files to `data/` (`fda_inspections.csv`, `fda_citations.csv`, and `fda_recall_events.csv`). It expects one worksheet per workbook, takes the first row as the CSV header, and skips entirely blank rows. It does not impose FDA-specific column schemas; table-specific validation belongs in the database loader.

To refresh the snapshot, download all three current FDA workbooks, put them in `data/raw/` under the canonical names above, and rerun the command. Preserve the downloaded workbooks so a refresh can be reproduced and reviewed.

## PostgreSQL tables

On the first database start, the scripts in `db/init/` validate and load the CSV files into the `fda` schema:

| Table | Row grain | Key |
|---|---|---|
| `fda.inspections` | One row per inspection | `inspection_id` |
| `fda.inspection_details` | One row per source inspection detail | Generated `detail_id`; joins by `inspection_id` |
| `fda.citations` | One row per citation | Generated `citation_id`; joins by `inspection_id` |
| `fda.recall_events` | One row per recall event | `event_id` |
| `fda.recalled_products` | One row per recalled product | `product_id`; joins by `event_id` |

Inspection exports repeat an inspection when project area or other detail fields differ. Recall exports repeat event attributes for each product; reason text and FDA detail links can vary by product, so those stay in `recalled_products`. The loader checks event- and inspection-level fields for consistency before collapsing them to one row per key. It also checks that citation IDs resolve and their repeated firm/date values agree with the inspection export.

Use `COUNT(DISTINCT inspection_id)` when counting inspections from `inspection_details`. The shared `FEI Number` identifies a firm, not a direct relationship between a particular inspection and recall. Avoid joining multiple detail tables before aggregating them, since their one-to-many rows can multiply counts. Count events from `fda.recall_events`, and products from `fda.recalled_products`.

The CSV loader uses PostgreSQL 17's `COPY ... HEADER MATCH` so changed or reordered source headers fail at the database boundary. Init scripts run only when Postgres creates a new data volume. To reload after refreshing the CSV snapshot, remove the database volume with `docker compose down -v` and start the stack again; this also deletes the current local database contents.
