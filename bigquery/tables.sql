-- ProductLoop BigQuery tables.
-- Run with the target dataset as the DEFAULT dataset; table names are unqualified on purpose.
-- Run order: tables.sql, then views/*.sql, then load seed data, then scheduled/signals.sql.

-- Reference: the controlled vocabulary, loaded from data/taxonomy_v2.json.
CREATE TABLE IF NOT EXISTS taxonomy_symptoms (
  symptom             STRING NOT NULL,
  issue_type          STRING NOT NULL,
  default_severity    STRING NOT NULL,
  safety              BOOL   NOT NULL,
  counts_as_complaint BOOL   NOT NULL,
  description         STRING,
  taxonomy_version    STRING
);

-- Production batches and what has shipped.
CREATE TABLE IF NOT EXISTS batches (
  batch_id            STRING NOT NULL,
  production_month    STRING,
  ship_start          DATE,
  units_shipped_india INT64,
  units_shipped_uk    INT64,
  units_shipped_total INT64
);

-- Units shipped per batch, region and week (installed base over time, for rates per 1,000 units).
CREATE TABLE IF NOT EXISTS shipments_weekly (
  batch_id   STRING NOT NULL,
  region     STRING NOT NULL,
  week_start DATE   NOT NULL,
  units      INT64  NOT NULL
);

-- Units whose owners registered them: the serial number gives the batch without the consumer typing it.
CREATE TABLE IF NOT EXISTS registered_units (
  serial_number STRING NOT NULL,
  batch_id      STRING,
  region        STRING,
  purchase_date DATE,
  consumer_id   STRING NOT NULL,
  unit_id       STRING,
  product_model STRING,
  registered_at TIMESTAMP,
  warranty_status STRING
);

-- One row per incident, including drafts. Count only submitted report_problem records
-- with counts_as_complaint = TRUE. region remains the country/market used for shipment rates.
-- Incident-location fields are separate; do not infer them from region without provenance.
-- Private columns (consumer_id, serial_number, raw_complaint)
-- are never exposed to the quality side; see views/.
CREATE TABLE IF NOT EXISTS complaints (
  complaint_id        STRING    NOT NULL,
  created_at          TIMESTAMP NOT NULL,
  updated_at          TIMESTAMP,
  consumer_id         STRING,
  unit_id             STRING,
  serial_number       STRING,
  batch_reference     STRING,
  region              STRING,
  incident_country    STRING,
  incident_region     STRING,
  incident_city       STRING,
  location_source     STRING,
  product_model       STRING,
  user_intent         STRING,
  input_types         ARRAY<STRING>,
  language            STRING,
  complaint_summary  STRING,
  service_appointment JSON,
  symptoms            ARRAY<STRING>,
  context             STRUCT<onset STRING, persists_after_cleaning STRING, during_charging BOOL>,
  issue_type          STRING,
  severity            STRING,
  safety_flag         BOOL,
  confidence          FLOAT64,
  counts_as_complaint BOOL,
  guidance_outcome    STRING,
  status              STRING,
  submitted_at        TIMESTAMP,
  resolved_at         TIMESTAMP,
  ticket_id           STRING,
  callback            STRUCT<status STRING, requested_at TIMESTAMP, scheduled_start TIMESTAMP, scheduled_end TIMESTAMP, time_zone STRING>,
  consent_share       BOOL,
  taxonomy_version    STRING
)
PARTITION BY DATE(created_at)
CLUSTER BY issue_type, batch_reference;

-- Audio, video and photo evidence. The files live in Cloud Storage; this holds the link.
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id      STRING NOT NULL,
  complaint_id     STRING NOT NULL,
  kind             STRING NOT NULL,
  gcs_uri          STRING,
  demo_file        STRING,
  duration_seconds INT64,
  consent_share    BOOL,
  created_at       TIMESTAMP,
  extraction_status STRING,
  extracted_symptoms ARRAY<STRING>,
  extracted_context STRUCT<onset STRING, persists_after_cleaning STRING, during_charging BOOL>,
  extracted_summary STRING,
  extraction_confidence FLOAT64,
  extraction_model STRING,
  extraction_model_version STRING,
  extraction_prompt_version STRING,
  extracted_at TIMESTAMP,
  consumer_id STRING,
  original_filename STRING,
  content_type STRING,
  storage_status STRING,
  storage_error STRING,
  stored_at TIMESTAMP
);

-- Append-only history linked by complaint_id; evidence_id is populated only for media events.
-- Stable event_id allows ingestion deduplication. BigQuery does not enforce uniqueness here.
-- event_type: report_submitted, evidence_added, classification_changed, resolved,
-- ticket_raised, callback_requested. Changes can carry before/after classification.
CREATE TABLE IF NOT EXISTS complaint_events (
  event_id STRING NOT NULL,
  complaint_id STRING NOT NULL,
  evidence_id STRING,
  occurred_at TIMESTAMP NOT NULL,
  event_type STRING NOT NULL,
  previous_status STRING,
  new_status STRING,
  previous_classification STRUCT<issue_type STRING, severity STRING, safety_flag BOOL>,
  new_classification STRUCT<issue_type STRING, severity STRING, safety_flag BOOL>,
  actor_type STRING,
  details JSON
)
PARTITION BY DATE(occurred_at)
CLUSTER BY complaint_id, event_type;

-- Knowledge-base passages with their embeddings, searched with VECTOR_SEARCH.
CREATE TABLE IF NOT EXISTS kb_chunks (
  chunk_id                STRING NOT NULL,
  product_model           STRING,
  source_file             STRING,
  section                 STRING,
  document_type           STRING,
  issue_types             ARRAY<STRING>,
  symptoms                ARRAY<STRING>,
  severity_applicability  ARRAY<STRING>,
  safety_critical         BOOL,
  title                   STRING,
  content                 STRING,
  embedding               ARRAY<FLOAT64>,
  embedding_model         STRING,
  taxonomy_version        STRING
);

-- One row of thresholds. as_of_date NULL means "today"; the demo data is pinned to a date.
CREATE TABLE IF NOT EXISTS signal_config (
  as_of_date          DATE,
  window_days         INT64   NOT NULL,
  baseline_days       INT64,
  min_events          INT64   NOT NULL,
  min_events_safety   INT64   NOT NULL,
  safety_share_min    FLOAT64 NOT NULL,
  growth_pct          FLOAT64 NOT NULL,
  watch_min_events    INT64   NOT NULL,
  watch_growth_pct    FLOAT64 NOT NULL,
  batch_rate_alerts_enabled BOOL,
  batch_multiple_flag FLOAT64 NOT NULL,
  min_batch_events    INT64   NOT NULL
);

-- Rule-based hypotheses. issue_type '*' matches any category. Placeholders in text are filled by signals.sql.
CREATE TABLE IF NOT EXISTS hypothesis_rules (
  rule_id            STRING NOT NULL,
  issue_type         STRING NOT NULL,
  min_batch_multiple FLOAT64,
  min_persists_share FLOAT64,
  specificity        INT64  NOT NULL,
  hypothesis         STRING NOT NULL,
  actions            ARRAY<STRING>,
  source_chunk_ids   ARRAY<STRING>
);

-- Written by the app when someone clicks "Open investigation".
CREATE TABLE IF NOT EXISTS investigations (
  investigation_id    STRING    NOT NULL,
  issue_type          STRING    NOT NULL,
  signal_computed_at  TIMESTAMP,
  created_at          TIMESTAMP NOT NULL,
  created_by          STRING,
  status              STRING    NOT NULL,
  actions             ARRAY<STRUCT<text STRING, done BOOL>>,
  notes               STRING
);


-- ---------------------------------------------------------------------------------------
-- Factory, service and returns data (investigation evidence). Fictional.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS production_batches (
  batch_id         STRING NOT NULL,
  plant            STRING,
  lines            ARRAY<STRING>,
  production_start DATE,
  production_end   DATE,
  units_produced   INT64
);

-- One supplier lot per component per batch, with change notes (new supplier, new tooling).
CREATE TABLE IF NOT EXISTS batch_lots (
  batch_id         STRING NOT NULL,
  component        STRING NOT NULL,
  lot_id           STRING NOT NULL,
  supplier         STRING,
  received_date    DATE,
  quantity         INT64,
  tooling_revision STRING,
  change_note      STRING
);

CREATE TABLE IF NOT EXISTS change_records (
  change_id   STRING NOT NULL,
  date        DATE,
  batch_id    STRING,
  type        STRING,
  description STRING,
  approved_by STRING
);

-- Sampled end-of-line tests (60 units per batch). Limits are in data/factory/spec_limits.json.
CREATE TABLE IF NOT EXISTS end_of_line_tests (
  unit_test_id           STRING NOT NULL,
  batch_id               STRING NOT NULL,
  test_date              DATE,
  line                   STRING,
  shift                  STRING,
  acoustic_db            FLOAT64,
  acoustic_limit_used_db FLOAT64,
  vibration_rms_mm_s     FLOAT64,
  lock_torque_nm         FLOAT64,
  surface_temp_c_5min    FLOAT64,
  battery_runtime_min    FLOAT64,
  burn_in_pass           BOOL,
  gate_result            STRING
);

CREATE TABLE IF NOT EXISTS service_repairs (
  repair_id           STRING NOT NULL,
  repair_date         DATE,
  batch_id            STRING,
  region              STRING,
  serial_number       STRING,
  complaint_id        STRING,
  service_centre      STRING,
  diagnosis           STRING,
  part_replaced       STRING,
  warranty_covered    BOOL,
  days_since_purchase INT64
);

CREATE TABLE IF NOT EXISTS product_returns (
  return_id     STRING NOT NULL,
  return_date   DATE,
  batch_id      STRING,
  region        STRING,
  serial_number STRING,
  complaint_id  STRING,
  reason_code   STRING,
  resolution    STRING
);

-- Count-based dashboard snapshot, maintained by app.services.signals.
CREATE TABLE IF NOT EXISTS signals (
  signal_id STRING,
  product_model STRING,
  issue_type STRING,
  computed_at TIMESTAMP,
  payload JSON
);
