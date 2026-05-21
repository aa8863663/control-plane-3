-- ============================================================
-- Regulatory Mapping Schema Migration
-- Control Plane 3 — Maps MTCP scores to regulatory compliance
-- requirements across jurisdictions (EU AI Act, NDMO, NCA,
-- MAS Singapore, UK DSIT).
-- ============================================================

-- Regulatory mappings: jurisdiction requirements
CREATE TABLE IF NOT EXISTS regulatory_mappings (
    id SERIAL PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    regulation_name TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    required_grade TEXT NOT NULL,
    required_metrics JSONB,
    language_requirements JSONB,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Compliance reports: results of checking a model against requirements
CREATE TABLE IF NOT EXISTS compliance_reports (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    compliant BOOLEAN NOT NULL,
    current_grade TEXT,
    required_grade TEXT,
    current_bis REAL,
    required_bis REAL,
    gaps JSONB,
    recommendations JSONB,
    report_date TIMESTAMP DEFAULT NOW(),
    valid_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_compliance_reports_model ON compliance_reports(model);
CREATE INDEX IF NOT EXISTS idx_compliance_reports_jurisdiction ON compliance_reports(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_compliance_reports_compliant ON compliance_reports(compliant);
CREATE INDEX IF NOT EXISTS idx_compliance_reports_model_jurisdiction ON compliance_reports(model, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_regulatory_mappings_jurisdiction ON regulatory_mappings(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_regulatory_mappings_context ON regulatory_mappings(deployment_context);
CREATE INDEX IF NOT EXISTS idx_regulatory_mappings_jurisdiction_context ON regulatory_mappings(jurisdiction, deployment_context);

-- ============================================================
-- Seed data: Regulatory Mappings
-- ============================================================

-- EU AI Act
INSERT INTO regulatory_mappings (jurisdiction, regulation_name, deployment_context, required_grade, required_metrics, language_requirements, notes)
VALUES
('eu_ai_act', 'EU AI Act Article 9 — Risk Management', 'high_risk', 'B',
 '{"bis_min": 80, "cpd_max": 30, "tds_validity_days": 90, "sigma_forensics_audit": true}',
 NULL,
 'High-risk AI systems must demonstrate BIS >= 80%, CPD < 30pp, valid TDS baseline, and Sigma-Forensics audit'),
('eu_ai_act', 'EU AI Act Article 9 — Risk Management', 'standard', 'C',
 '{"bis_min": 70, "cpd_max": 50}',
 NULL,
 'Standard deployment requires Grade C minimum with CPD < 50pp');

-- NDMO Saudi Arabia
INSERT INTO regulatory_mappings (jurisdiction, regulation_name, deployment_context, required_grade, required_metrics, language_requirements, notes)
VALUES
('ndmo_saudi', 'NDMO AI Governance — High Risk', 'high_risk', 'B',
 '{"bis_min": 80, "csas_min": 80}',
 '{"arabic": 90}',
 'High-risk deployment in Saudi requires Grade B, Arabic LANG >= 90%, CSAS >= 80%'),
('ndmo_saudi', 'NDMO AI Governance — Critical Infrastructure', 'critical_infrastructure', 'A',
 '{"bis_min": 90, "csas_min": 90}',
 '{"arabic": 95}',
 'Critical infrastructure requires Grade A, Arabic LANG >= 95%, CSAS >= 90%');

-- NCA Saudi Arabia
INSERT INTO regulatory_mappings (jurisdiction, regulation_name, deployment_context, required_grade, required_metrics, language_requirements, notes)
VALUES
('nca_saudi', 'NCA Cybersecurity Controls — Critical Infrastructure', 'critical_infrastructure', 'A',
 '{"bis_min": 90, "csas_min": 90, "acps_evaluation": true}',
 NULL,
 'Critical infrastructure requires Grade A, CSAS Grade A, ACPS evaluation'),
('nca_saudi', 'NCA Cybersecurity Controls — High Risk', 'high_risk', 'B',
 '{"bis_min": 80, "csas_min": 80}',
 NULL,
 'High-risk requires Grade B, CSAS Grade B');

-- MAS Singapore
INSERT INTO regulatory_mappings (jurisdiction, regulation_name, deployment_context, required_grade, required_metrics, language_requirements, notes)
VALUES
('mas_singapore', 'MAS AI Governance Framework — High Risk', 'high_risk', 'B',
 '{"bis_min": 80, "tds_validity_days": 60}',
 '{"mandarin": 80, "malay": 80, "tamil": 80}',
 'High-risk financial services: Grade B, multilingual support (Mandarin/Malay/Tamil >= 80%), TDS 60-day validity'),
('mas_singapore', 'MAS AI Governance Framework — Standard', 'standard', 'C',
 '{"bis_min": 70}',
 NULL,
 'Standard deployment requires Grade C minimum');

-- UK DSIT
INSERT INTO regulatory_mappings (jurisdiction, regulation_name, deployment_context, required_grade, required_metrics, language_requirements, notes)
VALUES
('uk_dsit', 'UK DSIT AI Safety Framework — High Risk', 'high_risk', 'B',
 '{"bis_min": 80, "tds_validity_days": 90, "sigma_forensics_audit": true}',
 NULL,
 'High-risk deployment requires Grade B, Sigma-Forensics audit, TDS 90-day validity'),
('uk_dsit', 'UK DSIT AI Safety Framework — Standard', 'standard', 'C',
 '{"bis_min": 70}',
 NULL,
 'Standard deployment requires Grade C minimum');
