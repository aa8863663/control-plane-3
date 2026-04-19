# evaluation-runner
---
name: evaluation-runner
version: 2026-04-19
triggers: [run evaluations, run probes, evaluate models, benchmark, run overnight]
tools: [bash, database]
constraints: [verify all writes, SHA-256 sign evidence packs, never contact openai]
---

## Purpose
Run MTCP probe evaluations against provider APIs. Verify all database
writes. Generate SHA-256 signed Evidence Packs. Report results.

## Process
1. Check which models need evaluation (missing temperature settings)
2. Load appropriate probe set (probes_200.json or probes_500.json)
3. Run evaluations via existing pipeline (runner.py or run_complete_partial.py)
4. Verify each database write
5. Generate Evidence Packs with SHA-256 signing
6. Update leaderboard
7. Write recap to WORKSPACE.md

## Provider Notes
- Bedrock: requires eu. prefix, max 1 concurrent model
- OpenAI: DO NOT RUN (ICO case active)
- All others: standard API calls via provider SDK

## Database
- Use psycopg2 with %s placeholders
- Always verify writes with SELECT after INSERT
- Check fetchone() for None before indexing
- runs table has both provider and api_provider columns

## Self-rewrite hook
After every run, log any API failures or rate limits to episodic memory.
Update provider notes if new issues encountered.
