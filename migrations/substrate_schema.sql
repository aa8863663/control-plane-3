-- Agent Substrate Measurement Schema
-- Framework F38: Four-vector holon measurement
-- Created: May 2026

CREATE TABLE IF NOT EXISTS substrate_knowledge_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    knowledge_integrity_score REAL NOT NULL,
    domains_tested INTEGER,
    domains_consistent INTEGER,
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS substrate_context_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    context_provenance_score REAL NOT NULL,
    providers_tested INTEGER,
    providers_consistent INTEGER,
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS substrate_schema_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    schema_persistence_score REAL NOT NULL,
    bis_mean REAL,
    grade TEXT,
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS substrate_projection_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    projection_consistency_score REAL NOT NULL,
    formats_tested INTEGER,
    formats_consistent INTEGER,
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sub_knowledge_model ON substrate_knowledge_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_sub_context_model ON substrate_context_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_sub_schema_model ON substrate_schema_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_sub_projection_model ON substrate_projection_scores(model_id);
