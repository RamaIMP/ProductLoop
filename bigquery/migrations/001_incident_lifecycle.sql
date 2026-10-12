-- Additive migration for existing datasets; use the intended DEFAULT dataset.
-- Does not overwrite data or backfill facts we cannot establish.
-- Run tables.sql after this migration to create complaint_events.
-- For a new dataset, tables.sql alone is sufficient.

ALTER TABLE complaints ADD COLUMN IF NOT EXISTS incident_country STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS incident_region STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS incident_city STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS location_source STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS status STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS ticket_id STRING;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS callback STRUCT<status STRING, requested_at TIMESTAMP, scheduled_start TIMESTAMP, scheduled_end TIMESTAMP, time_zone STRING>;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extraction_status STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extracted_symptoms ARRAY<STRING>;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extracted_context STRUCT<onset STRING, persists_after_cleaning STRING, during_charging BOOL>;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extracted_summary STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT64;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extraction_model STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extraction_model_version STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extraction_prompt_version STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMP;
