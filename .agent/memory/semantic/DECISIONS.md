# Major Research Decisions

## Architecture Decision Records (ADRs 0007-0015, April 2026)
- ADR-0007: External Validation Record — 6 practitioners validated in 48 hours (April 19-20 2026)
- ADR-0008: Ve as Reliability Signal Not Execution Rule — admissibility no longer reliably resolvable (Rihan)
- ADR-0009: Four Pattern Classification — P1 architectural (14), P2 stochastic (12), P3 genuine (2), P4 atypical (2)
- ADR-0010: Cross-Session BCF — unbounded, silent, permanent failure class (Timothy Cook)
- ADR-0011: URL Fabrication Disqualification — binary pass/fail gate for sovereign deployment
- ADR-0012: Parameter Count Invalid Proxy — larger does not mean better for constraint discipline
- ADR-0013: Commercial Framing — "governed at runtime vs bleed through" (Johnny Malik, 4Micro)
- ADR-0014: Fiscal Sponsorship Required — Schmidt Sciences deadline May 17, individuals ineligible
- ADR-0015: Substack Strategy — permanent public home, automated multi-platform pipeline
Files: research-estate/private/ADRs/ADR-00XX_*.md

## 2026-04-19: Public model count
Decision: Use 32 models, 13 providers publicly
Rationale: Paper I states 32 models from 13 providers. Database has 56 model/provider combinations due to same models running on multiple providers (e.g. claude-haiku on anthropic, bedrock, and openrouter). Unique deduplicated models = 32. Update paper needed before changing public claims.
Status: Active

## 2026-04-19: Probe count public claim
Decision: Use 200 primary + 20 control publicly per Paper I
Rationale: Database has 532 probes but Paper I states 200. Consistency with published work required.
Status: Active until update paper published

## 2026-04-19: OpenAI contact embargo
Decision: No contact with OpenAI in any form
Rationale: ICO case IC-421206-M4D8 active
Status: Active until ICO case resolved

## 2026-04-19: HuggingFace dataset
Decision: Full 181,448 row dataset uploaded
Rationale: Replaced 44-row aggregated file with full probe-level results
File: mtcp_500_full_results.csv
Status: Complete

## 2025-07-01: Research programme start
Decision: Independent research, no institutional affiliation
Rationale: Full intellectual freedom, no institutional constraints
Status: Active

## 2026-04-19: Agent infrastructure
Decision: Build .agent/ folder in control-plane-3
Rationale: Enable autonomous research pipeline using Claude Code
Status: In progress
