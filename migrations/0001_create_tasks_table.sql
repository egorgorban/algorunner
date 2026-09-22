CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    problem_text TEXT NOT NULL,
    language VARCHAR(2) NOT NULL,
    examples JSONB NOT NULL DEFAULT '[]'::jsonb,
    result JSONB,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
