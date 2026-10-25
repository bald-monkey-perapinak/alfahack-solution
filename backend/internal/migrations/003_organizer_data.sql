BEGIN;

CREATE TABLE dataset_imports (
    dataset_name TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    statistics JSONB NOT NULL DEFAULT '{}'
);

-- Derived index, not a replacement for the original payment observations.
-- An ambiguous repeated pair has no invented sum or concentration estimate.
CREATE TABLE payment_connections (
    payer_id BIGINT NOT NULL REFERENCES organizations(id),
    beneficiary_id BIGINT NOT NULL REFERENCES organizations(id),
    amount NUMERIC(24,2),
    payment_count BIGINT,
    observation_count INT NOT NULL CHECK (observation_count > 0),
    payer_share DOUBLE PRECISION CHECK (payer_share BETWEEN 0 AND 1),
    beneficiary_share DOUBLE PRECISION CHECK (beneficiary_share BETWEEN 0 AND 1),
    PRIMARY KEY (payer_id, beneficiary_id),
    CHECK (payer_id <> beneficiary_id)
);
CREATE INDEX idx_connections_out ON payment_connections(payer_id,payer_share DESC NULLS LAST);
CREATE INDEX idx_connections_in ON payment_connections(beneficiary_id,beneficiary_share DESC NULLS LAST);

COMMIT;
