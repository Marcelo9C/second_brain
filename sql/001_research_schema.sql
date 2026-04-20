CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    experiment_kind TEXT NOT NULL CHECK (experiment_kind IN ('chat', 'rag', 'embedding', 'evaluation')),
    title TEXT,
    study_label TEXT,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    model_name TEXT NOT NULL,
    embedding_model TEXT,
    seed BIGINT NOT NULL,
    temperature NUMERIC(6,4) NOT NULL,
    top_p NUMERIC(6,4) NOT NULL,
    top_k INTEGER NOT NULL,
    repeat_penalty NUMERIC(6,4),
    max_tokens INTEGER,
    chunk_size INTEGER NOT NULL,
    chunk_overlap INTEGER NOT NULL DEFAULT 0,
    corpus_version TEXT NOT NULL,
    prompt_template_version TEXT NOT NULL DEFAULT 'v1',
    retrieval_strategy TEXT NOT NULL DEFAULT 'none',
    retrieved_top_k INTEGER NOT NULL DEFAULT 0,
    prompt_messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT '{}'::text[],
    notes TEXT
);

CREATE INDEX IF NOT EXISTS experiments_created_at_idx
    ON research.experiments (created_at DESC);

CREATE INDEX IF NOT EXISTS experiments_model_name_idx
    ON research.experiments (model_name);

CREATE INDEX IF NOT EXISTS experiments_corpus_version_idx
    ON research.experiments (corpus_version);

CREATE INDEX IF NOT EXISTS experiments_study_label_idx
    ON research.experiments (study_label);

CREATE TABLE IF NOT EXISTS research.documents_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    title TEXT NOT NULL,
    section TEXT,
    source TEXT NOT NULL,
    document_date DATE,
    corpus_version TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0 CHECK (token_count >= 0),
    char_count INTEGER NOT NULL DEFAULT 0 CHECK (char_count >= 0),
    language_code TEXT,
    content_hash TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, corpus_version, chunk_index, embedding_model)
);

COMMENT ON COLUMN research.documents_chunks.embedding IS
    'Vector dimension fixed at 384 for the first research phase. If a future embedding model uses a different dimension, create a dedicated table or migrate the column type deliberately.';

CREATE INDEX IF NOT EXISTS documents_chunks_lookup_idx
    ON research.documents_chunks (corpus_version, source, title, section, document_date, chunk_index);

CREATE INDEX IF NOT EXISTS documents_chunks_metadata_idx
    ON research.documents_chunks
    USING GIN (metadata);

CREATE INDEX IF NOT EXISTS documents_chunks_embedding_idx
    ON research.documents_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS research.retrieval_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES research.experiments (id) ON DELETE CASCADE,
    document_chunk_id UUID REFERENCES research.documents_chunks (id) ON DELETE SET NULL,
    stage TEXT NOT NULL DEFAULT 'retrieve' CHECK (stage IN ('retrieve', 'rerank', 'prompt_context')),
    trace_rank INTEGER NOT NULL CHECK (trace_rank >= 1),
    prompt_rank INTEGER CHECK (prompt_rank IS NULL OR prompt_rank >= 1),
    selected_for_prompt BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT,
    document_date DATE,
    corpus_version TEXT NOT NULL,
    similarity_score DOUBLE PRECISION,
    lexical_score DOUBLE PRECISION,
    rerank_score DOUBLE PRECISION,
    chunk_text TEXT NOT NULL,
    chunk_token_count INTEGER,
    chunk_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (experiment_id, stage, trace_rank)
);

CREATE INDEX IF NOT EXISTS retrieval_traces_experiment_idx
    ON research.retrieval_traces (experiment_id, stage, trace_rank);

CREATE INDEX IF NOT EXISTS retrieval_traces_prompt_idx
    ON research.retrieval_traces (experiment_id, selected_for_prompt, prompt_rank);

CREATE TABLE IF NOT EXISTS research.annotations_sxs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    experiment_id UUID REFERENCES research.experiments (id) ON DELETE SET NULL,
    study_label TEXT,
    annotator TEXT NOT NULL DEFAULT 'human',
    prompt_original TEXT,
    system_prompt TEXT,
    prompt_original_a TEXT,
    prompt_original_b TEXT,
    system_prompt_a TEXT,
    system_prompt_b TEXT,
    output_a TEXT NOT NULL,
    output_b TEXT NOT NULL,
    candidate_a_label TEXT NOT NULL DEFAULT 'A',
    candidate_b_label TEXT NOT NULL DEFAULT 'B',
    candidate_a_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    candidate_b_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    factuality_a SMALLINT CHECK (factuality_a BETWEEN 1 AND 5),
    factuality_b SMALLINT CHECK (factuality_b BETWEEN 1 AND 5),
    helpfulness_a SMALLINT CHECK (helpfulness_a BETWEEN 1 AND 5),
    helpfulness_b SMALLINT CHECK (helpfulness_b BETWEEN 1 AND 5),
    grounding_a SMALLINT CHECK (grounding_a BETWEEN 1 AND 5),
    grounding_b SMALLINT CHECK (grounding_b BETWEEN 1 AND 5),
    chosen TEXT NOT NULL CHECK (chosen IN ('A', 'B')),
    rejected TEXT NOT NULL CHECK (rejected IN ('A', 'B') AND rejected <> chosen),
    rationale TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT '{}'::text[]
);

CREATE INDEX IF NOT EXISTS annotations_sxs_created_at_idx
    ON research.annotations_sxs (created_at DESC);

CREATE INDEX IF NOT EXISTS annotations_sxs_experiment_idx
    ON research.annotations_sxs (experiment_id);

CREATE INDEX IF NOT EXISTS annotations_sxs_chosen_idx
    ON research.annotations_sxs (chosen);

COMMENT ON TABLE research.experiments IS
    'Frozen experiment runs. Every row captures deterministic generation and retrieval settings.';

COMMENT ON TABLE research.documents_chunks IS
    'RAG chunk store with pgvector embeddings and rich metadata for pre-similarity filtering.';

COMMENT ON TABLE research.retrieval_traces IS
    'Immutable trace of which chunks were retrieved, reranked and sent to the model for a given experiment.';

COMMENT ON TABLE research.annotations_sxs IS
    'Structured side-by-side human preference annotations for RLHF and SFT dataset export.';
