CREATE SCHEMA fda;

CREATE TABLE fda.inspections (
  inspection_id text PRIMARY KEY,
  fei_number text NOT NULL,
  legal_name text NOT NULL,
  city text NOT NULL,
  state text NOT NULL,
  zip_code text NOT NULL,
  country_area text NOT NULL,
  fiscal_year smallint NOT NULL,
  posted_citations boolean NOT NULL,
  inspection_end_date date NOT NULL,
  fmd_145_date date
);

CREATE TABLE fda.inspection_details (
  detail_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  inspection_id text NOT NULL REFERENCES fda.inspections (inspection_id),
  classification text NOT NULL,
  project_area text NOT NULL,
  product_type text NOT NULL,
  additional_details text NOT NULL
);

CREATE TABLE fda.citations (
  citation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  inspection_id text NOT NULL REFERENCES fda.inspections (inspection_id),
  program_area text NOT NULL,
  act_cfr_number text NOT NULL,
  short_description text NOT NULL,
  long_description text
);

CREATE TABLE fda.recall_events (
  event_id text PRIMARY KEY,
  fei_number text NOT NULL,
  recalling_firm_name text NOT NULL,
  product_type text NOT NULL,
  status text NOT NULL,
  distribution_pattern text NOT NULL,
  recalling_firm_city text NOT NULL,
  recalling_firm_state text NOT NULL,
  recalling_firm_country text NOT NULL,
  center_classification_date date NOT NULL,
  event_classification text NOT NULL,
  center text NOT NULL
);

CREATE TABLE fda.recalled_products (
  product_id text PRIMARY KEY,
  event_id text NOT NULL REFERENCES fda.recall_events (event_id),
  product_classification text NOT NULL,
  product_description text NOT NULL,
  reason_for_recall text NOT NULL,
  recall_details text NOT NULL
);

CREATE INDEX inspections_fei_number_idx ON fda.inspections (fei_number);
CREATE INDEX inspections_fiscal_year_idx ON fda.inspections (fiscal_year);
CREATE INDEX inspection_details_inspection_id_idx ON fda.inspection_details (inspection_id);
CREATE INDEX inspection_details_product_type_idx ON fda.inspection_details (product_type);
CREATE INDEX citations_inspection_id_idx ON fda.citations (inspection_id);
CREATE INDEX citations_act_cfr_number_idx ON fda.citations (act_cfr_number);
CREATE INDEX recall_events_fei_number_idx ON fda.recall_events (fei_number);
CREATE INDEX recall_events_date_idx ON fda.recall_events (center_classification_date);
CREATE INDEX recalled_products_event_id_idx ON fda.recalled_products (event_id);
