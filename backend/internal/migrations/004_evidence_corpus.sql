BEGIN;

-- Searchable, source-preserving passages. A trigger also indexes material imported
-- through SQL by the organizer bootstrap or a future ingestion adapter.
CREATE TABLE material_passages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    material_id BIGINT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    body TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('russian', body)) STORED,
    UNIQUE (material_id, ordinal)
);
CREATE INDEX idx_material_passages_search ON material_passages USING GIN (search_vector);
CREATE INDEX idx_material_passages_material ON material_passages (material_id);

CREATE FUNCTION sync_material_passages() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM material_passages WHERE material_id = NEW.id;
    INSERT INTO material_passages(material_id, ordinal, body)
    SELECT NEW.id, part.ordinal::integer, btrim(part.body)
    FROM regexp_split_to_table(NEW.body, E'\n[[:space:]]*\n')
         WITH ORDINALITY AS part(body, ordinal)
    WHERE length(btrim(part.body)) >= 20;
    RETURN NEW;
END
$$;
CREATE TRIGGER materials_passages_sync
AFTER INSERT OR UPDATE OF body ON materials
FOR EACH ROW EXECUTE FUNCTION sync_material_passages();

INSERT INTO material_passages(material_id, ordinal, body)
SELECT m.id, part.ordinal::integer, btrim(part.body)
FROM materials m
CROSS JOIN LATERAL regexp_split_to_table(m.body, E'\n[[:space:]]*\n')
    WITH ORDINALITY AS part(body, ordinal)
WHERE length(btrim(part.body)) >= 20;

COMMIT;
