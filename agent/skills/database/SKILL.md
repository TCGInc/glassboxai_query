---
name: database
description: Guide to the FDA inspections, citations and recalls database - its five tables, row grains, keys, joins, coverage dates, data-quality pitfalls, and what the data does not contain. Read before writing any SQL or deciding whether a question can be answered.
---

# FDA compliance database

## What the data is
Three exports from the public FDA Data Dashboard (inspections, inspection citations, recalls), downloaded in October 2026 and loaded as a frozen snapshot into the `fda` schema. FDA says the exports contain finalized, posted records and are not comprehensive. The data is a snapshot: it ends in mid-October 2026 and says nothing about later events.

## Tables
| Table | One row per | Key | Rows |
|---|---|---|---|
| `inspections` | inspection | `inspection_id` | 277,312 |
| `inspection_details` | classification result for an inspection (one per project area / product type combination) | `detail_id`; `inspection_id` points to `inspections` | 344,373 |
| `citations` | citation (an observation inspectors recorded) | `citation_id`; `inspection_id` points to `inspections` | 282,395 |
| `recall_events` | recall event | `event_id` | 37,891 |
| `recalled_products` | product in a recall event | `product_id`; `event_id` points to `recall_events` | 104,673 |

Columns:
- `inspections`: `fei_number`, `legal_name`, `city`, `state`, `zip_code`, `country_area`, `fiscal_year`, `posted_citations` (true/false), `inspection_end_date`, `fmd_145_date`.
- `inspection_details`: `classification`, `project_area`, `product_type`, `additional_details`.
- `citations`: `program_area`, `act_cfr_number`, `short_description`, `long_description`.
- `recall_events`: `fei_number`, `recalling_firm_name`, `product_type`, `status`, `distribution_pattern`, `recalling_firm_city`, `recalling_firm_state`, `recalling_firm_country`, `center_classification_date`, `event_classification`, `center`.
- `recalled_products`: `product_classification`, `product_description`, `reason_for_recall`, `recall_details` (always a link to the FDA detail page, not narrative text).

## Joins
- Inspections, details and citations connect through `inspection_id`. Recall events and products connect through `event_id`.
- The inspection tables and the recall tables connect only through `fei_number`, which identifies a firm or facility. It does not tie a particular inspection to a particular recall, so a join on it describes the firm's history, not cause and effect. Of 10,284 firms with recalls, 7,915 also appear in the inspection data.
- Joining one-to-many tables multiplies rows. An inspection has up to 7 detail rows and usually several citations; a recall event has up to 470 products. Never join details and citations together before counting. Aggregate each separately, then combine the results.

## Pitfalls
- **What to count.** Counting rows of `inspection_details` counts inspection results, not inspections: 58,036 inspections have more than one detail row. Count distinct `inspection_id` for inspections. Likewise count `recall_events` rows for recall events and `recalled_products` rows for products.
- **Classification belongs to the detail rows.** An inspection has no single classification column. In 16,146 inspections the detail rows carry different classifications, and in 8,368 they span more than one product type. An inspection "has" a classification when at least one of its detail rows does.
- **Fiscal year.** `inspections.fiscal_year` is the federal fiscal year (October 1 to September 30, named for the year it ends); it always agrees with `inspection_end_date`. Inspection data covers fiscal years 2009 to 2027, but fiscal year 2027 holds only 48 inspections (October 1-14, 2026), so it is incomplete. Fiscal years 2020 and 2021 are unusually low (7,966 and 6,887 inspections against 14,000-17,000 in typical years). The recall tables have no fiscal year column; it must be derived from `center_classification_date`.
- **Recall coverage.** Recall dates run from 2012-06-08 to 2026-10-16, so fiscal year 2012 is incomplete and fiscal year 2027 holds only a few weeks.
- **Only one recall date exists.** `center_classification_date` is when the FDA center assigned the recall's class. There is no date for when the recall started, ended, or was posted.
- **Event and product classification.** `recall_events.event_classification` and `recalled_products.product_classification` usually agree. They differ for 2,735 products, always with the event at the more severe class. Use the event column when counting events and the product column when counting products.
- **Placeholders.** A dash (`-`) stands for "not applicable" in `inspections.state` (every non-U.S. inspection; 40,621 in all), in `recall_events.recalling_firm_state` for non-U.S. firms, and in `inspection_details.additional_details` (309,131 rows with nothing to add). `fmd_145_date` is NULL for 151,672 inspections. Only `long_description` (7 rows) and `fmd_145_date` can be NULL; other text columns are never empty.
- **Citations.** Only the 76,828 inspections with `posted_citations` true have citation rows (the flag and the rows always agree). Citations are observations an inspector recorded at the end of an inspection (Form 483); by FDA's own wording they are not a final determination of compliance. `citations.program_area` uses different names from `product_type` (for example "Foods" against "Food/Cosmetics").
- **Names.** Within this data one `fei_number` has one `inspections.legal_name`, but 1,222 firms appear under more than one `recalling_firm_name`. Group by `fei_number`, not by name. Names and places are free text as FDA published them; use pattern matching for partial names. `reason_for_recall` and `product_description` are free text too.
- **Values are stored in full words.** For example classifications are stored as "No Action Indicated (NAI)", states as full names ("California"), and countries as FDA writes them ("United States", "Korea (the Republic of)"). The terminology skill lists the exact values.

## What the data does not contain
Warning letters, seizures, injunctions and other compliance actions; import alerts and import refusals; inspection start dates, inspectors, or the findings of an inspection beyond its classification and citations; recall start or end dates, quantities, distribution counts, injuries or illnesses; drug identifiers such as NDC numbers; fines or penalties; firm size or ownership; and anything after October 2026. Questions that need these cannot be answered from this database.
