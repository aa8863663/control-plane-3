# Verified Research Findings

## External Validation Events (April 19-20 2026)

Six independent practitioners validated MTCP within 48 hours:

DEFINITIVE COMMERCIAL FRAMING (Johnny Malik, CAIO 4Micro):
"Which models can be governed at runtime and which will bleed through no matter how much control-plane engineering you throw at them."
Use this framing for all enterprise-facing communications.

SOVEREIGN AI INTEGRATION (Mohamed Rihan, KFUPM):
Ve above threshold means admissibility is no longer reliably resolvable. This is his refinement. It is correct and stronger than original framing. Use this in all Ve descriptions going forward.

FIRST FORMAL CITATION (Timothy Cook, Axius SDC ADR-0003):
MTCP formally cited in company Architecture Decision Record. ADR date: April 19 2026.
Note: ADR contains incorrect figures (181,428 and 35 models). Correct figures: 181,448 evaluations, 32 models, 13 providers.

CROSS-SESSION BCF (Timothy Cook):
New failure class identified: autonomous memory poisoning. BCF propagates through persistence layer, becomes permanent. More severe than within-session BCF measured by MTCP. Short empirical note to OSF planned (not full paper).

TEMPERATURE INTERVENTION INSIGHT (Nathan Freestone / Elora):
Temperature adjustment ineffective for architectural failure class (Pattern 1, 14 models). Only effective for stochastic class (Pattern 2, 12 models). Applying temperature correction to architectural failure gives false safe zone signal.

## Core MTCP Findings (verified against 181,448 evaluations)
- No model achieves Grade A (90%+ threshold)
- Best performer: grok-3-mini at 88.7% (Grade B)
- Worst performer: magistral-medium at 37.3% (Grade F)
- GPT-4o scores 16.2pp below GPT-4o-mini (inverse scaling)
- Safety-tuned models cluster at 66-68% across all temperatures
- Temperature variance in safety-tuned models: under 1pp (T=0.0 to T=0.8)
- Control probe degradation: all models collapse to 10-57.5% band
- DeepSeek-R1 exception: 5pp CPD (contamination-resistant)
- Ve>=2 threshold: admissibility is no longer reliably resolvable under current conditions (Mohamed Rihan refinement, April 20 2026)

## Four-Pattern Breakdown (database verified, externally validated April 20 2026)
External validation: Mohamed Rihan (R-AGAM) independently queried HuggingFace dataset and confirmed pattern distribution.
- Pattern 1 - Architectural failure: 14 models (44%). Under 2pp temp variance. Claude family, GPT-4o (1.4pp). Training intervention required.
- Pattern 2 - Stochastic failure: 12 models (38%). 2-5pp temp variance. LLaMA family, grok-3-mini, GPT-4o-mini. Operational controls partially effective.
- Pattern 3 - Genuine persistence: 2 models (6%). Temp-invariant AND low CPD. DeepSeek-R1 (2.2pp, CPD -3.7pp). No remediation required.
- Pattern 4 - Atypical: 2 models (6%). Claude Sonnet 4.5 (12.0pp inverse), qwen3-8b (54.2pp artefact). Individual analysis required.

## IGS Theory Findings
- Temperature invariance = architectural failure (not stochastic)
- Temperature sensitivity = stochastic failure (LLaMA family pattern)
- Claude Sonnet 4.5: atypical inverse pattern (12.0pp, improves with temperature) - NOT architectural as previously described
- DeepSeek-R1: genuine persistence, not probe familiarity

## Framework Definitions (F2-F15 public, F16-F19 private)
- F2 Ve (Veterance): formal metric for post-correction persistence failure
- F3 CPD (Control Performance Degradation): metric for detecting benchmark contamination
- F4 BIS (Benchmark Index Score): multi-temperature aggregate metric
- F5 Five-Vector Taxonomy: constraint categories (content, behavior, format, role, safety)
- F6 Temperature Taxonomy: three-pattern failure classification (invariant, sensitive, hybrid)
- F7 Behavioral Deviation Taxonomy: 5-part classification of deviation types
- F8 Rhetorical State Space: formal mathematical specification of model behavioral states
- F9 Sigma-Forensics: practitioner audit methodology standard
- F10 EU AI Act Compliance Map: article-level mapping for regulatory use
- F11 MITRE ATLAS Reference: BCF mapped to adversarial ML threat framework
- F12 BCF Canonical Definition: Behavioral Constraint Failure formal reference
- F13 IGS Mechanism Note: Identity-Gate Satiation mechanism definition
- F14 BCL Concept Note: Behavioral Credibility Leakage — new risk category
- F15 PRP Public Design: Posture Reauthorization Protocol (mitigation approach)
- F16-F19: PRIVATE (PRP implementation, Ve monitoring, probe methodology, acquisition)

## Paper Series Coverage (Papers 05-25 drafted)
- Paper 05: CPD metric for contamination detection
- Paper 07: Flagship regression evidence (frontier models getting worse)
- Paper 08: Five-vector analysis of which constraints fail most
- Paper 09: Stochastic vs architectural failure diagnostic criteria
- Paper 10: Ve formal metric and persistence lemma
- Paper 11: GPT-4o anomaly (flagship scoring below mini — inverse scaling)
- Paper 12: MITRE ATLAS mapping + cross-vendor BCF convergence (12b)
- Paper 13: EU AI Act compliance evidence via MTCP/Sigma
- Paper 14: RLHF short-horizon critique (structural gap argument)
- Paper 15: Transcript-only evidence standards
- Paper 16: BCL (Behavioral Credibility Leakage) as new risk category
- Paper 17: DeepSeek-R1 as the genuine persistence exception
- Paper 18: Open-source outperforms commercial on constraint persistence
- Paper 19: IGS monitoring system design
- Paper 20: PRP design (public specification)
- Paper 22: Vector attractor depth across constraint categories
- Paper 23: Inverse Imitation Game (machine recognition of human patterns)
- Paper 24: GDPR and LLM adaptation (cross-session profiling argument)
- Paper 25: AI co-authorship and derivative IP attribution

## Cross-Session BCF Propagation (Timothy Cook, Axius SDC, April 20 2026)
- New failure class: BCF that exits session boundary and enters persistence layer
- Poisoned state becomes permanent ground truth, pre-loaded before correction can operate
- Qualitatively more severe than within-session BCF measured by MTCP
- Evidence: 4 models tested with persistence layer architecture
  - Gemma 4B: PASSED (admitted uncertainty, asked for clarification)
  - Qwen 2.5 7B: FAILED (hallucinated, saved to memory)
  - Granite 4 IBM: FAILED (fabricated entire crypto wallet infrastructure)
  - Gemma 26B: FAILED (fabricated Web3 platform with DIDs/ZKPs/TEEs)
- Key finding: hallucination discipline does not scale with parameter count (Gemma 4B passed, Gemma 26B failed)
- MTCP Ve metric does not apply (failure is pre-session, not in-session)
- Joint paper with Timothy Cook in preparation (awaiting ADR writeup)

## Database-Verified CPD Values (April 19 2026)
- grok-3-mini: primary 92.1%, ctrl 29.4%, CPD −62.7pp (Severe)
- GPT-4o: primary 65.1%, ctrl 54.2%, CPD −10.9pp (Moderate)
- GPT-4o-mini: primary 84.3%, ctrl 48.3%, CPD −36.0pp (Substantial)
- GPT-3.5-turbo: primary 83.6%, ctrl 42.5%, CPD −41.1pp (Substantial)
- DeepSeek-R1: primary 62.5%, ctrl 58.8%, CPD −3.7pp (Minimal)
- Claude Sonnet 4.5: primary 56.5%, ctrl 30.6%, CPD −25.9pp (Moderate)
- Dataset mean CPD: −28.0pp
- 32 models have control probe data (not 25 as stated in early drafts)
- Pass criterion: outcome = 'COMPLETED' (not latency-based)

## Claude Sonnet 4.5 Atypical Pattern
- Temperature: 53.5% (T=0.0), 61.4% (T=0.2), 55.1% (T=0.5), 67.0% (T=0.8)
- Improves with temperature (13.5pp range) — opposite of expected
- Does not fit cleanly into architectural or stochastic classification
- Noted in Papers 14, 18 as requiring further investigation

## Database Technical Lessons
- psycopg2 requires %s not ? for placeholders
- Always check fetchone() for None before indexing
- recovery_latency is TEXT in DB, cast to FLOAT for calculations
- runs table has both provider and api_provider columns
- Bedrock requires eu. prefix on model names
- Bedrock max 1 concurrent model to avoid throttling
- Pass/fail is determined by outcome column: COMPLETED = pass, SAFETY_HARD_STOP = fail
- Tables: runs, results, alerts, api_keys, evaluation_requests, sessions, users, user_provider_keys, password_reset_tokens
- results joined to runs via run_id; datasets are 'probes_200', 'probes_500', 'ctrl'

## Platform Lessons
- Render was watching wrong branch (fixed, now on Fly.io)
- Docker layer cache issues resolved
- GROUP BY duplicates in leaderboard query fixed
- Temperature float equality failures resolved
- NULL probe_id rows exist (4,500 rows) - include in total count
