# Major Research Decisions

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
