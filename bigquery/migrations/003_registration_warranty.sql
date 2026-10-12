-- Store the supplied warranty status; do not infer coverage from purchase date.
ALTER TABLE registered_units ADD COLUMN IF NOT EXISTS warranty_status STRING;
