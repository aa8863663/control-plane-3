-- ============================================================
-- ACPS (Adversarial Constraint Persistence Score) Schema Migration
-- Control Plane 3 — Tests whether constraint persistence holds
-- under active adversarial attack (prompt injection, jailbreak
-- pressure, authority spoofing, context flooding).
-- ============================================================

-- Evaluations: one row per ACPS test run
CREATE TABLE IF NOT EXISTS acps_evaluations (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    constraint_type TEXT NOT NULL,
    temperature REAL DEFAULT 0.0,
    probe_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Attacks: individual adversarial probe results
CREATE TABLE IF NOT EXISTS acps_attacks (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES acps_evaluations(id),
    probe_id TEXT NOT NULL,
    attack_type TEXT NOT NULL,
    attack_severity TEXT NOT NULL,
    constraint_survived BOOLEAN NOT NULL,
    failure_mode TEXT,
    response_excerpt TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Failures: detailed failure records for audit
CREATE TABLE IF NOT EXISTS acps_failures (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES acps_evaluations(id),
    attack_id INTEGER REFERENCES acps_attacks(id),
    failure_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Scores: aggregated ACPS scores per evaluation
CREATE TABLE IF NOT EXISTS acps_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES acps_evaluations(id),
    acps REAL NOT NULL,
    grade TEXT NOT NULL,
    injection_resistance REAL,
    jailbreak_resistance REAL,
    authority_resistance REAL,
    context_resistance REAL,
    adversarial_gap REAL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_acps_evaluations_model ON acps_evaluations(model);
CREATE INDEX IF NOT EXISTS idx_acps_attacks_evaluation_id ON acps_attacks(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_acps_attacks_attack_type ON acps_attacks(attack_type);
CREATE INDEX IF NOT EXISTS idx_acps_failures_evaluation_id ON acps_failures(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_acps_failures_failure_type ON acps_failures(failure_type);
CREATE INDEX IF NOT EXISTS idx_acps_scores_evaluation_id ON acps_scores(evaluation_id);
