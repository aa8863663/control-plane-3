# audit-runner
---
name: audit-runner
version: 2026-04-19
triggers: [audit, check numbers, verify, what is the status]
tools: [bash, database]
constraints: [use verified numbers only, A. Abby pseudonym]
---

## Purpose
Full audit of MTCP research estate. Verify all numbers match across
database, platform, papers, and public claims.

## Process
1. Query database for exact counts (evaluations, models, providers, probes)
2. Check platform health at mtcp.live
3. Verify Paper I figures match public claims
4. Check all pending applications and deadlines
5. Report discrepancies
6. Update WORKSPACE.md with current status

## Database Query
import psycopg2, os
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM results")
cur.execute("SELECT COUNT(DISTINCT model) FROM runs")
cur.execute("SELECT COUNT(DISTINCT provider) FROM runs")
cur.execute("SELECT COUNT(DISTINCT probe_id) FROM results WHERE probe_id IS NOT NULL")

## Verified Numbers (April 19 2026)
- Total evaluations: 181,448
- Unique probes: 532
- Public claim: 32 models, 13 providers
- Database actual: 56 model/provider combinations, 14 providers

## Self-rewrite hook
After every audit, check if numbers have changed. Update LESSONS.md
and DECISIONS.md if new models or providers have been added.
