-- ============================================================
-- TDS (Temporal Drift Score) Schema Migration
-- Control Plane 3 — Detects silent performance degradation
-- from model updates or provider changes over time.
-- ============================================================

-- TDS baselines: store a model's BIS at a known evaluation point
CREATE TABLE IF NOT EXISTS tds_baselines (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    dataset TEXT NOT NULL DEFAULT 'probes_500',
    bis REAL NOT NULL,
    grade TEXT NOT NULL,
    temperature REAL,
    evaluated_at TIMESTAMP NOT NULL,
    valid_until TIMESTAMP,
    run_ids TEXT[],
    created_at TIMESTAMP DEFAULT NOW()
);

-- TDS comparisons: compare current evaluation against baseline
CREATE TABLE IF NOT EXISTS tds_comparisons (
    id SERIAL PRIMARY KEY,
    baseline_id INTEGER REFERENCES tds_baselines(id),
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    current_bis REAL NOT NULL,
    current_grade TEXT NOT NULL,
    tds REAL NOT NULL,
    drift_velocity REAL,
    drift_class TEXT NOT NULL,
    days_elapsed INTEGER,
    evaluated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- TDS alerts: triggered when drift exceeds threshold
CREATE TABLE IF NOT EXISTS tds_alerts (
    id SERIAL PRIMARY KEY,
    comparison_id INTEGER REFERENCES tds_comparisons(id),
    model TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    drift_class TEXT NOT NULL,
    tds REAL NOT NULL,
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- TDS schedules: when to re-evaluate each model
CREATE TABLE IF NOT EXISTS tds_schedules (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 90,
    last_evaluated TIMESTAMP,
    next_evaluation TIMESTAMP,
    auto_run BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_tds_baselines_model ON tds_baselines(model);
CREATE INDEX IF NOT EXISTS idx_tds_baselines_provider ON tds_baselines(provider);
CREATE INDEX IF NOT EXISTS idx_tds_baselines_model_provider ON tds_baselines(model, provider);
CREATE INDEX IF NOT EXISTS idx_tds_comparisons_model ON tds_comparisons(model);
CREATE INDEX IF NOT EXISTS idx_tds_comparisons_provider ON tds_comparisons(provider);
CREATE INDEX IF NOT EXISTS idx_tds_comparisons_drift_class ON tds_comparisons(drift_class);
CREATE INDEX IF NOT EXISTS idx_tds_comparisons_baseline ON tds_comparisons(baseline_id);
CREATE INDEX IF NOT EXISTS idx_tds_alerts_model ON tds_alerts(model);
CREATE INDEX IF NOT EXISTS idx_tds_alerts_drift_class ON tds_alerts(drift_class);
CREATE INDEX IF NOT EXISTS idx_tds_alerts_comparison ON tds_alerts(comparison_id);
CREATE INDEX IF NOT EXISTS idx_tds_schedules_model ON tds_schedules(model);
CREATE INDEX IF NOT EXISTS idx_tds_schedules_provider ON tds_schedules(provider);
CREATE INDEX IF NOT EXISTS idx_tds_schedules_next ON tds_schedules(next_evaluation);
