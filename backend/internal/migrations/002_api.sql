BEGIN;

ALTER TABLE users ADD COLUMN email TEXT UNIQUE;
ALTER TABLE users ADD COLUMN password_hash TEXT;
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

ALTER TABLE sources ADD CONSTRAINT sources_name_type_unique UNIQUE(name, source_type);
ALTER TABLE materials ADD COLUMN analysis_data JSONB NOT NULL DEFAULT '{}'
    CHECK (jsonb_typeof(analysis_data)='object');
ALTER TABLE materials ADD COLUMN content_hash TEXT;
ALTER TABLE materials ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX idx_materials_hash ON materials(content_hash);

CREATE TABLE analysis_jobs (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    target_role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
    parameters JSONB NOT NULL CHECK (jsonb_typeof(parameters)='object'),
    idempotency_key TEXT,
    lease_owner UUID,
    heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_code TEXT,
    summary JSONB NOT NULL DEFAULT '{}',
    UNIQUE(user_id, idempotency_key)
);
CREATE INDEX idx_jobs_queue ON analysis_jobs(created_at) WHERE status='pending';
CREATE INDEX idx_jobs_user ON analysis_jobs(user_id, created_at DESC);
ALTER TABLE analysis_runs ADD COLUMN job_id UUID REFERENCES analysis_jobs(id);
CREATE INDEX idx_runs_job ON analysis_runs(job_id);
ALTER TABLE insights ADD COLUMN payload JSONB NOT NULL DEFAULT '{}';
CREATE TABLE insight_feedback (
    user_id BIGINT NOT NULL REFERENCES users(id),
    insight_id BIGINT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK (rating IN ('useful','not_useful','already_known')),
    comment TEXT CHECK (length(comment)<=2000),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id, insight_id)
);
COMMIT;
