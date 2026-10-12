-- Additive columns only. Existing records are not overwritten or backfilled.
ALTER TABLE registered_units ADD COLUMN IF NOT EXISTS unit_id STRING;
ALTER TABLE registered_units ADD COLUMN IF NOT EXISTS product_model STRING;
ALTER TABLE registered_units ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP;
ALTER TABLE complaints ADD COLUMN IF NOT EXISTS unit_id STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS consumer_id STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS original_filename STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS content_type STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS storage_status STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS storage_error STRING;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS stored_at TIMESTAMP;
