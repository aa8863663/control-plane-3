# Verified Research Findings

## Core MTCP Findings (verified against 181,448 evaluations)
- No model achieves Grade A (90%+ threshold)
- Best performer: grok-3-mini at 88.7% (Grade B)
- Worst performer: magistral-medium at 37.3% (Grade F)
- GPT-4o scores 16.2pp below GPT-4o-mini (inverse scaling)
- Safety-tuned models cluster at 66-68% across all temperatures
- Temperature variance in safety-tuned models: under 1pp (T=0.0 to T=0.8)
- Control probe degradation: all models collapse to 10-57.5% band
- DeepSeek-R1 exception: 5pp CPD (contamination-resistant)
- Ve>=2 threshold: recovery without session reset becomes empirically unlikely

## IGS Theory Findings
- Temperature invariance = architectural failure (not stochastic)
- Temperature sensitivity = stochastic failure (LLaMA family pattern)
- Claude models: architectural IGS signature confirmed
- DeepSeek-R1: genuine persistence, not probe familiarity

## Database Technical Lessons
- psycopg2 requires %s not ? for placeholders
- Always check fetchone() for None before indexing
- recovery_latency is TEXT in DB, cast to FLOAT for calculations
- runs table has both provider and api_provider columns
- Bedrock requires eu. prefix on model names
- Bedrock max 1 concurrent model to avoid throttling

## Platform Lessons
- Render was watching wrong branch (fixed, now on Fly.io)
- Docker layer cache issues resolved
- GROUP BY duplicates in leaderboard query fixed
- Temperature float equality failures resolved
- NULL probe_id rows exist (4,500 rows) - include in total count
