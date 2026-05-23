-- Runtime Monitoring Schema
-- Framework F36: PRP Live Wrapper and session coherence
-- Created: May 2026

-- Individual turn observations
CREATE TABLE IF NOT EXISTS runtime_observations (
    id SERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    constraint_id TEXT,
    turn_number INTEGER NOT NULL,
    compliant BOOLEAN NOT NULL,
    response_hash TEXT NOT NULL,
    rolling_bis REAL,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Session coherence records
CREATE TABLE IF NOT EXISTS session_coherence_records (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    model_id TEXT NOT NULL,
    constraint_id TEXT,
    turn_count INTEGER NOT NULL,
    final_rolling_bis REAL NOT NULL,
    baseline_bis REAL,
    drift_delta REAL,
    coherence_hash TEXT NOT NULL,
    status TEXT DEFAULT 'closed',
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Active sessions tracker
CREATE TABLE IF NOT EXISTS runtime_sessions (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    model_id TEXT NOT NULL,
    constraint_id TEXT,
    deployment_context TEXT DEFAULT 'general_enterprise',
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    turn_count INTEGER DEFAULT 0,
    compliant_turns INTEGER DEFAULT 0,
    rolling_bis REAL DEFAULT 1.0,
    baseline_bis REAL,
    drift_tolerance REAL DEFAULT 0.10
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_runtime_obs_session ON runtime_observations(session_id);
CREATE INDEX IF NOT EXISTS idx_runtime_obs_model ON runtime_observations(model_id);
CREATE INDEX IF NOT EXISTS idx_runtime_obs_request ON runtime_observations(request_id);
CREATE INDEX IF NOT EXISTS idx_session_coherence_model ON session_coherence_records(model_id);
CREATE INDEX IF NOT EXISTS idx_session_coherence_session ON session_coherence_records(session_id);
CREATE INDEX IF NOT EXISTS idx_runtime_sessions_model ON runtime_sessions(model_id);
CREATE INDEX IF NOT EXISTS idx_runtime_sessions_status ON runtime_sessions(status);
