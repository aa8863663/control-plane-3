-- Governance Alert System Schema
-- Monitors all governance metrics and fires alerts when thresholds are crossed
-- Created: May 2026

CREATE TABLE IF NOT EXISTS governance_alerts (
    id SERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,          -- 'tds_critical', 'csas_degradation', 'jrs_expired', 'gate_expired', 'bec_integrity'
    model_id TEXT NOT NULL,
    provider TEXT,
    threshold_crossed TEXT NOT NULL,   -- description of what threshold
    current_value REAL,
    threshold_value REAL,
    severity TEXT NOT NULL DEFAULT 'warning',  -- 'info', 'warning', 'critical'
    details JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT,
    alert_timestamp TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_governance_alerts_model ON governance_alerts(model_id);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_type ON governance_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_resolved ON governance_alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_governance_alerts_severity ON governance_alerts(severity);
