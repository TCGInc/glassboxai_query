\set ON_ERROR_STOP on

CREATE TEMP TABLE stg_inspections (
  "FEI Number" text,
  "Legal Name" text,
  "City" text,
  "State" text,
  "Zip" text,
  "Country/Area" text,
  "Fiscal Year" text,
  "Inspection ID" text,
  "Posted Citations" text,
  "Inspection End Date" text,
  "Classification" text,
  "Project Area" text,
  "Product Type" text,
  "Additional Details" text,
  "FMD-145 Date" text
);

CREATE TEMP TABLE stg_citations (
  "Inspection ID" text,
  "FEI Number" text,
  "Legal Name" text,
  "Inspection End Date" text,
  "Program Area" text,
  "Act/CFR Number" text,
  "Short Description" text,
  "Long Description" text
);

CREATE TEMP TABLE stg_recall_products (
  "FEI Number" text,
  "Recalling Firm Name" text,
  "Product Type" text,
  "Product Classification" text,
  "Status" text,
  "Distribution Pattern" text,
  "Recalling Firm City" text,
  "Recalling Firm State" text,
  "Recalling Firm Country" text,
  "Center Classification Date" text,
  "Reason for Recall" text,
  "Product Description" text,
  "Event ID" text,
  "Event Classification" text,
  "Product ID" text,
  "Center" text,
  "Recall Details" text
);

COPY stg_inspections FROM '/data/fda_inspections.csv'
  WITH (FORMAT csv, HEADER MATCH, ENCODING 'UTF8');
COPY stg_citations FROM '/data/fda_citations.csv'
  WITH (FORMAT csv, HEADER MATCH, ENCODING 'UTF8');
COPY stg_recall_products FROM '/data/fda_recall_events.csv'
  WITH (FORMAT csv, HEADER MATCH, ENCODING 'UTF8');

-- Give the planner real statistics for the validation queries below.
ANALYZE stg_inspections;
ANALYZE stg_citations;
ANALYZE stg_recall_products;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM stg_inspections
    WHERE NULLIF(BTRIM("Inspection ID"), '') IS NULL
       OR NULLIF(BTRIM("FEI Number"), '') IS NULL
       OR NULLIF(BTRIM("Legal Name"), '') IS NULL
       OR NULLIF(BTRIM("City"), '') IS NULL
       OR NULLIF(BTRIM("State"), '') IS NULL
       OR NULLIF(BTRIM("Zip"), '') IS NULL
       OR NULLIF(BTRIM("Country/Area"), '') IS NULL
       OR NULLIF(BTRIM("Fiscal Year"), '') IS NULL
       OR NULLIF(BTRIM("Posted Citations"), '') IS NULL
       OR NULLIF(BTRIM("Inspection End Date"), '') IS NULL
       OR NULLIF(BTRIM("Classification"), '') IS NULL
       OR NULLIF(BTRIM("Project Area"), '') IS NULL
       OR NULLIF(BTRIM("Product Type"), '') IS NULL
       OR NULLIF(BTRIM("Additional Details"), '') IS NULL
       OR LOWER(BTRIM("Posted Citations")) NOT IN ('yes', 'no')
       OR "Inspection End Date" !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} 00:00:00$'
       OR (BTRIM("FMD-145 Date") NOT IN ('', '-')
           AND "FMD-145 Date" !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} 00:00:00$')
  ) THEN
    RAISE EXCEPTION 'Inspection export has a blank required value or invalid Posted Citations';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM stg_inspections
    GROUP BY "Inspection ID"
    HAVING COUNT(DISTINCT "FEI Number") > 1
        OR COUNT(DISTINCT "Legal Name") > 1
        OR COUNT(DISTINCT "City") > 1
        OR COUNT(DISTINCT "State") > 1
        OR COUNT(DISTINCT "Zip") > 1
        OR COUNT(DISTINCT "Country/Area") > 1
        OR COUNT(DISTINCT "Fiscal Year") > 1
        OR COUNT(DISTINCT "Posted Citations") > 1
        OR COUNT(DISTINCT "Inspection End Date") > 1
        OR COUNT(DISTINCT "FMD-145 Date") > 1
  ) THEN
    RAISE EXCEPTION 'Inspection-level fields vary within an Inspection ID';
  END IF;

  IF EXISTS (
    SELECT 1 FROM stg_citations c
    LEFT JOIN (SELECT DISTINCT "Inspection ID" FROM stg_inspections) i
      USING ("Inspection ID")
    WHERE NULLIF(BTRIM(c."Inspection ID"), '') IS NULL
       OR NULLIF(BTRIM(c."Program Area"), '') IS NULL
       OR NULLIF(BTRIM(c."Act/CFR Number"), '') IS NULL
       OR NULLIF(BTRIM(c."Short Description"), '') IS NULL
       OR i."Inspection ID" IS NULL
  ) THEN
    RAISE EXCEPTION 'Citation references a blank or unknown Inspection ID';
  END IF;

  -- Inspection-level fields were just shown to be constant within an Inspection
  -- ID, so joining the detail rows directly is equivalent to joining distinct
  -- inspections. Use count(*) rather than EXISTS: the planner expects EXISTS on
  -- this OR to find a mismatch quickly, picks a nested loop, and never finishes.
  IF (
    SELECT COUNT(*)
    FROM stg_citations c
    JOIN stg_inspections i USING ("Inspection ID")
    WHERE c."FEI Number" IS DISTINCT FROM i."FEI Number"
       OR c."Legal Name" IS DISTINCT FROM i."Legal Name"
       OR c."Inspection End Date" IS DISTINCT FROM i."Inspection End Date"
  ) > 0 THEN
    RAISE EXCEPTION 'Citation firm or date fields do not match the inspection export';
  END IF;

  IF EXISTS (
    SELECT 1 FROM stg_recall_products
    WHERE NULLIF(BTRIM("Event ID"), '') IS NULL
       OR NULLIF(BTRIM("Product ID"), '') IS NULL
       OR NULLIF(BTRIM("FEI Number"), '') IS NULL
       OR NULLIF(BTRIM("Recalling Firm Name"), '') IS NULL
       OR NULLIF(BTRIM("Product Type"), '') IS NULL
       OR NULLIF(BTRIM("Event Classification"), '') IS NULL
       OR NULLIF(BTRIM("Product Classification"), '') IS NULL
       OR NULLIF(BTRIM("Status"), '') IS NULL
       OR NULLIF(BTRIM("Distribution Pattern"), '') IS NULL
       OR NULLIF(BTRIM("Recalling Firm City"), '') IS NULL
       OR NULLIF(BTRIM("Recalling Firm State"), '') IS NULL
       OR NULLIF(BTRIM("Recalling Firm Country"), '') IS NULL
       OR NULLIF(BTRIM("Center Classification Date"), '') IS NULL
       OR NULLIF(BTRIM("Reason for Recall"), '') IS NULL
       OR NULLIF(BTRIM("Product Description"), '') IS NULL
       OR NULLIF(BTRIM("Center"), '') IS NULL
       OR NULLIF(BTRIM("Recall Details"), '') IS NULL
       OR "Center Classification Date" !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} 00:00:00$'
  ) THEN
    RAISE EXCEPTION 'Recall export has a blank required identifier or classification';
  END IF;

  IF EXISTS (
    SELECT 1 FROM stg_recall_products
    GROUP BY "Product ID" HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'Recall Product ID is not unique';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM stg_recall_products
    GROUP BY "Event ID"
    HAVING COUNT(DISTINCT "FEI Number") > 1
        OR COUNT(DISTINCT "Recalling Firm Name") > 1
        OR COUNT(DISTINCT "Product Type") > 1
        OR COUNT(DISTINCT "Status") > 1
        OR COUNT(DISTINCT "Distribution Pattern") > 1
        OR COUNT(DISTINCT "Recalling Firm City") > 1
        OR COUNT(DISTINCT "Recalling Firm State") > 1
        OR COUNT(DISTINCT "Recalling Firm Country") > 1
        OR COUNT(DISTINCT "Center Classification Date") > 1
        OR COUNT(DISTINCT "Event Classification") > 1
        OR COUNT(DISTINCT "Center") > 1
  ) THEN
    RAISE EXCEPTION 'Event-level fields vary within a Recall Event ID';
  END IF;
END
$$;

INSERT INTO fda.inspections (
  inspection_id, fei_number, legal_name, city, state, zip_code, country_area,
  fiscal_year, posted_citations, inspection_end_date, fmd_145_date
)
SELECT DISTINCT ON ("Inspection ID")
  "Inspection ID",
  "FEI Number",
  "Legal Name",
  "City",
  "State",
  "Zip",
  "Country/Area",
  "Fiscal Year"::smallint,
  LOWER(BTRIM("Posted Citations")) = 'yes',
  LEFT("Inspection End Date", 10)::date,
  CASE WHEN BTRIM("FMD-145 Date") IN ('', '-') THEN NULL
       ELSE LEFT("FMD-145 Date", 10)::date END
FROM stg_inspections
ORDER BY "Inspection ID";

INSERT INTO fda.inspection_details (
  inspection_id, classification, project_area, product_type, additional_details
)
SELECT "Inspection ID", "Classification", "Project Area", "Product Type", "Additional Details"
FROM stg_inspections;

INSERT INTO fda.citations (
  inspection_id, program_area, act_cfr_number, short_description, long_description
)
SELECT "Inspection ID", "Program Area", "Act/CFR Number", "Short Description", "Long Description"
FROM stg_citations;

INSERT INTO fda.recall_events (
  event_id, fei_number, recalling_firm_name, product_type, status,
  distribution_pattern, recalling_firm_city, recalling_firm_state,
  recalling_firm_country, center_classification_date, event_classification, center
)
SELECT DISTINCT ON ("Event ID")
  "Event ID",
  "FEI Number",
  "Recalling Firm Name",
  "Product Type",
  "Status",
  "Distribution Pattern",
  "Recalling Firm City",
  "Recalling Firm State",
  "Recalling Firm Country",
  LEFT("Center Classification Date", 10)::date,
  "Event Classification",
  "Center"
FROM stg_recall_products
ORDER BY "Event ID";

INSERT INTO fda.recalled_products (
  product_id, event_id, product_classification, product_description,
  reason_for_recall, recall_details
)
SELECT "Product ID", "Event ID", "Product Classification", "Product Description",
       "Reason for Recall", "Recall Details"
FROM stg_recall_products;

ANALYZE fda.inspections;
ANALYZE fda.inspection_details;
ANALYZE fda.citations;
ANALYZE fda.recall_events;
ANALYZE fda.recalled_products;

SELECT 'inspections' AS table_name, COUNT(*) AS row_count FROM fda.inspections
UNION ALL SELECT 'inspection_details', COUNT(*) FROM fda.inspection_details
UNION ALL SELECT 'citations', COUNT(*) FROM fda.citations
UNION ALL SELECT 'recall_events', COUNT(*) FROM fda.recall_events
UNION ALL SELECT 'recalled_products', COUNT(*) FROM fda.recalled_products
ORDER BY table_name;
