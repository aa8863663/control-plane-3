-- DRA (Deployment Readiness Attestation) Schema
-- Framework F34: Composite pre-deployment fidelity score
-- Created: May 2026

-- DRA scores table
CREATE TABLE IF NOT EXISTS dra_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    dra_score REAL NOT NULL,
    dra_grade TEXT NOT NULL,
    bis_score REAL,
    bis_weight REAL DEFAULT 0.4,
    tds_valid BOOLEAN,
    tds_weight REAL DEFAULT 0.2,
    bec_integrity REAL,
    bec_weight REAL DEFAULT 0.2,
    gate_status TEXT,
    gate_weight REAL DEFAULT 0.2,
    computed_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Signed attestation records
CREATE TABLE IF NOT EXISTS dra_attestations (
    id SERIAL PRIMARY KEY,
    attestation_id TEXT UNIQUE NOT NULL,
    model_id TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    dra_score REAL NOT NULL,
    dra_grade TEXT NOT NULL,
    attested_at TIMESTAMP DEFAULT NOW(),
    attested_by TEXT DEFAULT 'mtcp_system',
    attestation_hash TEXT NOT NULL,
    valid_until TIMESTAMP,
    status TEXT DEFAULT 'active'
);

-- Context threshold log
CREATE TABLE IF NOT EXISTS dra_context_log (
    id SERIAL PRIMARY KEY,
    deployment_context TEXT NOT NULL,
    min_grade TEXT NOT NULL,
    min_score REAL NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dra_scores_model ON dra_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_dra_scores_context ON dra_scores(deployment_context);
CREATE INDEX IF NOT EXISTS idx_dra_scores_grade ON dra_scores(dra_grade);
CREATE INDEX IF NOT EXISTS idx_dra_attestations_model ON dra_attestations(model_id);
CREATE INDEX IF NOT EXISTS idx_dra_attestations_status ON dra_attestations(status);
CREATE INDEX IF NOT EXISTS idx_dra_context_log_context ON dra_context_log(deployment_context);

-- Seed context thresholds
INSERT INTO dra_context_log (deployment_context, min_grade, min_score, description) VALUES
    ('critical_infrastructure', 'A', 0.90, 'Critical infrastructure requires Grade A'),
    ('financial_services', 'B', 0.80, 'Financial services requires Grade B'),
    ('healthcare', 'B', 0.80, 'Healthcare requires Grade B'),
    ('government_services', 'B', 0.80, 'Government services requires Grade B'),
    ('general_enterprise', 'C', 0.70, 'General enterprise requires Grade C')
ON CONFLICT DO NOTHING;
