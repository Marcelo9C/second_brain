CREATE TABLE IF NOT EXISTS research.rubric_generation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES research.localization_rubric_cases(id) ON DELETE CASCADE,
    run_number INT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'success', 'failed', 'rejected_by_validation', 'discarded')
    ),
    provider_requested TEXT,
    model_requested TEXT,
    provider_used TEXT,
    model_used TEXT,
    model_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_snapshot_hash TEXT,
    prompt_text TEXT,
    raw_model_response TEXT,
    parsed_rubrics JSONB,
    validation_report JSONB,
    heuristic_report JSONB,
    approx_prompt_tokens INT,
    approx_response_tokens INT,
    duration_ms INT,
    response_status TEXT,
    exact_url_called TEXT,
    error_message TEXT,
    parent_run_id UUID REFERENCES research.rubric_generation_runs(id),
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(case_id, run_number)
);

CREATE INDEX IF NOT EXISTS rubric_generation_runs_case_id_idx
    ON research.rubric_generation_runs (case_id, run_number DESC);

CREATE INDEX IF NOT EXISTS rubric_generation_runs_status_idx
    ON research.rubric_generation_runs (status);

CREATE INDEX IF NOT EXISTS rubric_generation_runs_model_idx
    ON research.rubric_generation_runs (provider_requested, model_requested);

CREATE TABLE IF NOT EXISTS research.rubric_generation_applied_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES research.localization_rubric_cases(id) ON DELETE CASCADE,
    run_id UUID REFERENCES research.rubric_generation_runs(id),
    rubrics_snapshot JSONB NOT NULL,
    validation_report JSONB,
    heuristic_report JSONB,
    human_quality_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    human_quality_reviewed_by TEXT,
    human_quality_reviewed_at TIMESTAMPTZ,
    human_quality_notes TEXT,
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS rubric_generation_applied_artifacts_case_id_idx
    ON research.rubric_generation_applied_artifacts (case_id, applied_at DESC);

CREATE INDEX IF NOT EXISTS rubric_generation_applied_artifacts_run_id_idx
    ON research.rubric_generation_applied_artifacts (run_id);
