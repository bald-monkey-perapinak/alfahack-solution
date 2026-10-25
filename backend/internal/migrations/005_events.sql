BEGIN;

-- Each event has a real source publication as its stable anchor.
CREATE TABLE news_events (
    id BIGINT PRIMARY KEY REFERENCES materials(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE materials ADD COLUMN event_id BIGINT REFERENCES news_events(id);
CREATE INDEX idx_materials_event ON materials(event_id) WHERE event_id IS NOT NULL;

-- Existing publications remain distinct until they can be compared using the
-- same guarded matching rules as newly ingested material.
INSERT INTO news_events(id)
SELECT id FROM materials WHERE material_type='news';
UPDATE materials SET event_id=id WHERE material_type='news';

COMMIT;
