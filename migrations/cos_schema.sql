-- COS (Constraint Object Specification) Schema
-- Framework F31: Governed constraint as a formal object
-- Created: May 2026

-- Primary constraint objects table
CREATE TABLE IF NOT EXISTS cos_objects (
    id SERIAL PRIMARY KEY,
    constraint_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    provenance JSONB NOT NULL,
    scope JSONB NOT NULL,
    validity_conditions JSONB NOT NULL,
    inheritance_rules JSONB NOT NULL,
    expiry TIMESTAMP,
    registered_at TIMESTAMP DEFAULT NOW(),
    registered_by TEXT DEFAULT 'mtcp_system',
    status TEXT DEFAULT 'active',
    version INTEGER DEFAULT 1
);

-- Constraint registry for lookup and comparison
CREATE TABLE IF NOT EXISTS cos_registry (
    id SERIAL PRIMARY KEY,
    constraint_id TEXT NOT NULL REFERENCES cos_objects(constraint_id),
    model_id TEXT,
    evaluation_id TEXT,
    linked_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Inheritance log for coordination chains
CREATE TABLE IF NOT EXISTS cos_inheritance_log (
    id SERIAL PRIMARY KEY,
    parent_constraint_id TEXT NOT NULL,
    child_constraint_id TEXT NOT NULL,
    boundary_id TEXT,
    inherited_at TIMESTAMP DEFAULT NOW(),
    inheritance_type TEXT DEFAULT 'full',
    notes TEXT
);

-- Validity check records
CREATE TABLE IF NOT EXISTS cos_validity_checks (
    id SERIAL PRIMARY KEY,
    constraint_id TEXT NOT NULL REFERENCES cos_objects(constraint_id),
    checked_at TIMESTAMP DEFAULT NOW(),
    is_valid BOOLEAN NOT NULL,
    reason TEXT,
    checked_by TEXT DEFAULT 'mtcp_system'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cos_objects_status ON cos_objects(status);
CREATE INDEX IF NOT EXISTS idx_cos_objects_expiry ON cos_objects(expiry);
CREATE INDEX IF NOT EXISTS idx_cos_registry_constraint ON cos_registry(constraint_id);
CREATE INDEX IF NOT EXISTS idx_cos_registry_model ON cos_registry(model_id);
CREATE INDEX IF NOT EXISTS idx_cos_registry_eval ON cos_registry(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_cos_inheritance_parent ON cos_inheritance_log(parent_constraint_id);
CREATE INDEX IF NOT EXISTS idx_cos_inheritance_child ON cos_inheritance_log(child_constraint_id);
CREATE INDEX IF NOT EXISTS idx_cos_validity_constraint ON cos_validity_checks(constraint_id);
