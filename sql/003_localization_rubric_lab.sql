CREATE SCHEMA IF NOT EXISTS research;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS research.localization_rubric_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    locale TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('Writing', 'Chitchat', 'Knowledge')),
    chat_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt TEXT,
    response_raw TEXT,
    golden_response TEXT,
    evaluator_notes TEXT,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL DEFAULT 'v1',
    rubrics JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'approved', 'exported')),
    tags TEXT[] NOT NULL DEFAULT '{}'::text[],
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS localization_rubric_cases_updated_at_idx
    ON research.localization_rubric_cases (updated_at DESC);

CREATE INDEX IF NOT EXISTS localization_rubric_cases_locale_category_idx
    ON research.localization_rubric_cases (locale, category);

CREATE INDEX IF NOT EXISTS localization_rubric_cases_status_idx
    ON research.localization_rubric_cases (status);

CREATE INDEX IF NOT EXISTS localization_rubric_cases_metadata_idx
    ON research.localization_rubric_cases
    USING GIN (metadata);

COMMENT ON TABLE research.localization_rubric_cases IS
    'Localization Trial rubric drafts, reviews, approvals and exports for MLOps workflows.';
