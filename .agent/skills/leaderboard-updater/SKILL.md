# leaderboard-updater
---
name: leaderboard-updater
version: 2026-04-19
triggers: [update leaderboard, refresh platform, check leaderboard, leaderboard]
tools: [bash, database]
constraints: [verify all writes, use Paper I public figures]
---

## Purpose
Pull latest results from database, update mtcp.live leaderboard,
flag any anomalies or unexpected results.

## Process
1. Query database for latest completed runs
2. Calculate BIS scores per model per temperature
3. Calculate average BIS across temperatures
4. Assign grades (A+ to F)
5. Check for anomalies (unexpected score changes)
6. Update leaderboard via platform API or direct DB update
7. Log changes to episodic memory

## Grading Scale
- A+: 95%+
- A: 90%+
- B: 80%+
- C: 70%+
- D: 60%+
- F: below 60%

## Anomaly Flags
- Score change >10pp from previous run: flag for review
- Temperature variance >5pp: flag as stochastic pattern
- Temperature variance <1pp: flag as architectural pattern

## Self-rewrite hook
After every update, check if any models have changed tier.
Log significant changes to semantic/LESSONS.md.
