BEGIN;

ALTER TABLE items ADD COLUMN IF NOT EXISTS image_content_type VARCHAR(30);
ALTER TABLE items ADD COLUMN IF NOT EXISTS image_size INTEGER;
ALTER TABLE items ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;

ALTER TABLE items DROP CONSTRAINT IF EXISTS items_status_check;
ALTER TABLE items ADD CONSTRAINT items_status_check
    CHECK (status IN ('ACTIVE', 'HANDOVER_IN_PROGRESS', 'RESOLVED', 'CLOSED'));

CREATE INDEX IF NOT EXISTS items_active_type_idx ON items (item_type, status, created_at DESC);

COMMIT;
