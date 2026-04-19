# paper-writer
---
name: paper-writer
version: 2026-04-19
triggers: [write paper, draft paper, paper on, extend paper, finish paper]
tools: [bash, database]
preconditions: [DATABASE_URL set, Papers I II III accessible]
constraints: [A. Abby pseudonym only, never disclose F16-F19, use verified numbers]
---

## Purpose
Draft extension papers (Papers 04-25) from database findings, framework
documentation, and existing research. Match style and rigour of Papers I, II, III.

## Style Reference
- Paper I: empirical, data-forward, specific numbers, benchmark results
- Paper II: theoretical, framework-building, falsifiable predictions
- Paper III: applied, regulatory-mapped, practical methodology

## Process
1. Query database for relevant findings
2. Load relevant framework from files/ directory
3. Read semantic/LESSONS.md for verified findings
4. Load closest style reference paper
5. Draft structure:
   - Abstract (250 words max)
   - Introduction (context and gap)
   - Methodology (reference MTCP protocol)
   - Findings (data from database with exact numbers)
   - Discussion (IGS theory application)
   - Conclusion (implications and next steps)
   - References
6. Save draft to files/drafts/PaperXX_DRAFT.md
7. Log to episodic memory
8. Update WORKSPACE.md

## Quality Checks
- All numbers sourced from database or verified documents
- No real name used anywhere
- No proprietary IP (F16-F19, probe content, constraint_detector.py)
- Consistent with Paper I published figures for public claims
- Falsifiable claims only
- A. Abby author name on all papers

## Self-rewrite hook
After every 3 papers, check style consistency with published papers.
