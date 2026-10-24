---
name: terminology
description: Maps FDA and analyst vocabulary - NAI/VAI/OAI, recall Classes I-III, recall status, FEI, FDA centers, fiscal year, Form 483 citations - to this database's columns and exact stored values, and sets defaults for everyday phrasing such as "inspections" and "recalls". Read before interpreting a question.
---

# FDA terminology and how it appears in the data

## Inspection outcomes (column `inspection_details.classification`)
| Term | Stored value | Meaning |
|---|---|---|
| NAI | `No Action Indicated (NAI)` | No objectionable conditions found. A "clean" inspection. |
| VAI | `Voluntary Action Indicated (VAI)` | Objectionable conditions found, but FDA is not recommending regulatory action; the firm is expected to correct them voluntarily. |
| OAI | `Official Action Indicated (OAI)` | Significant objectionable conditions; FDA recommends regulatory action. The most serious outcome. |

Everyday phrases: "clean" or "passed" means NAI. "Problems found" or "objectionable conditions" means VAI or OAI together. "Failed", "bad" and "worst" are not FDA terms and the data has no pass/fail field, so they do not map to a classification. OAI only and VAI plus OAI give different numbers, and which one is meant is the user's call: ask rather than choose.

## Inspection vocabulary
- **FEI (FDA Establishment Identifier):** the number that identifies a firm or facility, column `fei_number` in both inspections and recalls.
- **Inspection vs inspection result:** an inspection is one row of `inspections`. An inspection result is one row of `inspection_details`. "How many inspections" means distinct inspections. When asked about an outcome, count the distinct inspections that have at least one result with that classification, and say that is the unit. "Inspection results" or "results" means counting `inspection_details` rows.
- **Project area (`project_area`):** the FDA program the inspection work belongs to, for example "Drug Quality Assurance" or "Foodborne Biological Hazards". There are 24 values.
- **Product type (`product_type`):** `Food/Cosmetics` (food and cosmetics together), `Devices` (medical devices), `Drugs`, `Biologics` (such as blood products, vaccines, cell and gene therapies), `Veterinary`, `Tobacco`. "Food" means `Food/Cosmetics`; the data cannot separate food from cosmetics at this level.
- **Additional details (`additional_details`):** an optional note on the kind of inspection, such as `FSVP` (Foreign Supplier Verification Program), `Clinical Investigator (CI)`, `IRB` (institutional review board) or `Sponsor, Contract Research Organization`. A dash means none.
- **`fmd_145_date`:** a date field in the FDA export tied to FDA Field Management Directive 145. The export does not define it further, so do not interpret it beyond its name.
- **Domestic and foreign:** domestic means `country_area` is "United States"; foreign means any other value. "Overseas" means foreign.

## Citations (table `citations`)
- A citation here is an inspectional observation, the kind listed on FDA Form 483 at the end of an inspection. "Observations", "483s", "citations" and (loosely) "violations" all map to citation rows. These are not final legal findings, so avoid calling them violations in an answer.
- `act_cfr_number` is the regulation cited (for example `21 CFR 820.100(a)`, about quality system procedures for devices). `short_description` is FDA's short label for it. `program_area` is the regulated area: Foods, Devices, Drugs, Veterinary Medicine, Bioresearch Monitoring, Biologics, Human Tissue for Transplantation, Parts 1240 and 1250, Radiologic Health, Part 11 Compliance.
- "How many citations" counts citation rows. "How many inspections had citations" counts distinct inspections (these are the inspections with `posted_citations` true).

## Recalls
- **Class (`event_classification`, `product_classification`):** `Class I` is a situation where there is a reasonable probability that using or being exposed to the product will cause serious adverse health consequences or death; the most serious. `Class II` is where use or exposure may cause temporary or medically reversible adverse health consequences, or the chance of serious consequences is remote. `Class III` is where use or exposure is not likely to cause adverse health consequences. "Dangerous" or "most serious" recalls means Class I.
- **Status (`recall_events.status`):** `Ongoing` (recall actions are still being carried out), `Completed` (the firm finished its recall actions, and FDA has not yet terminated the recall), `Terminated` (FDA has determined the firm took all reasonable steps, and the recall is closed). "Open" or "active" recalls most naturally means `Ongoing`; "closed" most naturally means `Terminated`.
- **Event vs product:** a recall event can cover many products. "How many recalls" means recall events (rows of `recall_events`). "How many products were recalled" means rows of `recalled_products`. Say which one you counted.
- **"Products in Class I recall events" vs "Class I products":** the first means products that belong to events whose `event_classification` is Class I. The second means products whose own `product_classification` is Class I. The two differ for some products, so say which one you used.
- **`center_classification_date`:** the date the FDA center classified the recall. It is the only recall date, and it is not the date the recall began.
- **Centers (`recall_events.center`)** and their `product_type`: CDRH (Center for Devices and Radiological Health) is Devices; CBER (Biologics Evaluation and Research) is Biologics; CDER (Drug Evaluation and Research) is Drugs; CVM (Veterinary Medicine) is Veterinary; CTP (Tobacco Products) is Tobacco; CFSAN (Food Safety and Applied Nutrition), HFP (Human Foods Program, the successor to CFSAN) and OCS all map to Food/Cosmetics. Both CFSAN and HFP appear in the data, so a question about food recalls should include both.
- **Reason for recall (`reason_for_recall`):** free text on why the product was recalled. Topic questions (for example Salmonella, undeclared allergens, sterility) are answered by searching this text, and the result depends on the search words, so say which words were used.

## Time
- **Fiscal year (FY):** the U.S. federal fiscal year runs October 1 to September 30 and is named for the calendar year in which it ends. FY 2025 is 2024-10-01 through 2025-09-30. `inspections.fiscal_year` already holds it. For recalls it must be derived from `center_classification_date`.
- **Calendar year:** January 1 to December 31. If a question says "in 2024" without "fiscal", it is most naturally a calendar year, but mention that choice. Relative phrases such as "last year", "recently" or "this year" are ambiguous: the data ends in October 2026, and the calendar and fiscal readings differ.

## Places
- States are stored as full names ("California"), with a dash for non-U.S. locations. Countries are stored as FDA writes them, such as "United States", "China", "India", "Korea (the Republic of)", "Hong Kong SAR".
