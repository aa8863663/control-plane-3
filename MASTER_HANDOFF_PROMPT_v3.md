# CONTROL PLANE 3 — MASTER HANDOFF PROMPT v3
# Paste this entire file at the start of any new AI conversation to continue this project.
# Last updated: March 2026 — Platform live, PostgreSQL migrated, UI redesigned.

---

## WHO IS THE USER

Aimee (A. Abby for research purposes). Non-technical — always explain in plain English first, then give exact copy-paste terminal commands one at a time. Never chain long commands together. She is deploying a proprietary LLM safety evaluation platform she built from scratch with AI assistance.

---

## WHAT IS BUILT

**Control Plane 3** — a black-box LLM safety evaluation platform implementing the **MTCP protocol (Multi-Turn Constraint Persistence)**. Novel framework measuring whether LLMs maintain compliance with explicit constraints across structured correction sequences. First platform of its kind.

**Registered Research:** DOI: https://doi.org/10.17605/OSF.IO/DXGK5
**All Rights Reserved © 2026 A. Abby**
**GitHub:** https://github.com/aa8863663/control-plane-3 (PRIVATE)
**Live URL:** https://control-plane-3.onrender.com

---

## TECH STACK

- Python 3.9, FastAPI, PostgreSQL (Neon), Jinja2, Uvicorn
- Dockerfile + render.yaml — deployed on Render.com
- Auth: session-based + API key dual auth
- Local path: ~/Downloads/cp3/
- Start server: `cd ~/Downloads/cp3 && export $(cat .env | xargs) && python3 -m uvicorn api_server:app --reload`
- Default login: admin / [CHANGED — Aimee knows the password]
- Backup: ~/Downloads/controlplane3_backup/

---

## DATABASE

**Production:** Neon PostgreSQL (permanent, never wipes)
- Connection string is set as `DATABASE_URL` environment variable on Render
- Neon project: control-plane-3
- 4,128 results imported and live

**Local:** SQLite at ~/Downloads/cp3/controlplane.db
- Also has all 4,128 results imported from CSVs
- Used for local testing only

---

## ALL FILES

| File | Purpose |
|---|---|
| api_server.py | FastAPI server, all routes — uses psycopg2/Neon |
| llm_safety_platform.py | Multi-model benchmark runner |
| auth.py | User authentication |
| api_keys.py | API key management |
| user_api_keys.py | Encrypted per-user LLM key storage |
| certification.py | MTCP grade engine A+ to F |
| constraint_detector.py | Semantic violation detection |
| ve_engine.py | Violation engine |
| prp_engine.py | Persistence policy, hard stop trigger |
| artifact_writer.py | Audit trail logging |
| actuarial_metrics.py | Risk quantification |
| report_generator.py | PDF/CSV report generation |
| certificate_pdf.py | PDF certificate generator (reportlab) |
| probes_200.json | 252 probes across 5 vectors — NEVER make public |
| controlplane.db | Local SQLite — all results (backup only) |
| migrate_to_neon.py | Migration script (already run, keep for reference) |
| Dockerfile | Production Docker build |
| render.yaml | Render.com deployment config |
| templates/ | All HTML templates — dark fintech UI |
| controlplane3-landing.html | Public landing page |

---

## TEMPLATES (all redesigned — dark fintech UI)

| Template | Status |
|---|---|
| base.html | Shared nav + design system (Syne + JetBrains Mono fonts) |
| index.html | Dashboard — stat cards, model performance, key findings |
| leaderboard.html | Rankings table with grades and progress bars |
| certificate.html | Certificate cards with grade, stats, DOI |
| login.html | Clean centred login page |
| stats.html | Run statistics |
| costs.html | Usage breakdown by model/temperature |
| admin.html | User management, password change |
| landing.html | Public landing page — hero, results table, enquiry form |

---

## DASHBOARD ROUTES (all working)

| URL | Page |
|---|---|
| / | Home dashboard |
| /landing | Public landing page |
| /leaderboard | Model rankings |
| /certificate | MTCP compliance certificates |
| /certificate/download/{model}/{temperature} | PDF certificate download |
| /stats | Run statistics |
| /costs | Usage breakdown |
| /admin | User + API key management |
| /api/export-csv | Download all results |
| /docs | OpenAPI documentation |

---

## BENCHMARK RESULTS — COMPLETE (March 2026)

### LLaMA 3.1 8B (llama-3.1-8b-instant, Groq) ✅
| Temp | Pass Rate | Hard Stops | Grade |
|---|---|---|---|
| 0.0 | 72.2% | 70 | C |
| 0.2 | 75.0% | 63 | C |
| 0.5 | 71.0% | 73 | C |
| 0.8 | 67.9% | 81 | D |

### LLaMA 3.3 70B (llama-3.3-70b-versatile, Groq) ✅
| Temp | Pass Rate | Hard Stops | Grade |
|---|---|---|---|
| 0.0 | 76.6% | 59 | C |
| 0.2 | 74.6% | 64 | C |
| 0.5 | 75.8% | 61 | C |
| 0.8 | 75.4% | 62 | C |

### Claude Sonnet 4 (claude-sonnet-4-20250514, Anthropic) ✅
| Temp | Pass Rate | Hard Stops | Grade |
|---|---|---|---|
| 0.0 | 67.9% | 81 | D |
| 0.2 | 68.7% | 79 | D |
| 0.5 | 67.9% | 81 | D |
| 0.8 | 67.9% | 81 | D |

### Claude Haiku 4.5 (claude-haiku-4-5-20251001, Anthropic) ✅
| Temp | Pass Rate | Hard Stops | Grade |
|---|---|---|---|
| 0.0 | 66.7% | 84 | D |
| 0.2 | 65.5% | 87 | D |
| 0.5 | 65.1% | 88 | D |
| 0.8 | 67.1% | 83 | D |

**Total: 16 runs, 4,128 probe evaluations, 4 models, 4 temperatures**

---

## KEY FINDINGS

1. **Open source beats paid Claude** — LLaMA 3.3 70B avg 75.6% (C) vs Claude Sonnet 4 avg 68.1% (D)
2. **Temperature resistance in Claude** — only 2% variance across T=0.0–0.8. Systematic failure.
3. **Temperature sensitivity in LLaMA** — LLaMA 3.1 8B drops 7 points T=0.2 to T=0.8
4. **No model passes MTCP** — highest grade is C

---

## WHAT WAS DONE TODAY (6 March 2026)

✅ All 16 leaderboard/certificate/stats/landing/costs/admin routes fixed
✅ Full dark fintech UI redesign (Syne + JetBrains Mono, base.html design system)
✅ PostgreSQL migration to Neon (permanent database, no more wiping on redeploy)
✅ 4,128 results imported into both Neon and local SQLite
✅ PDF certificate generator built (certificate_pdf.py using reportlab)
✅ Professional landing page with results table and enquiry form
✅ Admin password changed (strong)
✅ SECRET_KEY made permanent on Render
✅ Blank/legacy model names cleaned up in DB
✅ Paper Table 5 filled in (MTCP_paper_Abby_2026_v1_4_1_FINAL_updated.docx)
✅ Local backup at ~/Downloads/controlplane3_backup/

---

## WHAT STILL NEEDS DOING (priority order)

### 🔴 Immediate

**1. Formspree — activate landing page contact form**
- Go to formspree.io and sign up with motets.film-7p@icloud.com
- Create a new form
- Copy the form ID (looks like xpzgkwqr)
- In templates/landing.html find this line:
  `action="https://formspree.io/f/motets.film-7p@icloud.com"`
- Replace with:
  `action="https://formspree.io/f/YOUR_FORM_ID"`
- Push to GitHub

**2. Upload paper to OSF**
- Go to osf.io/dxgk5 and log in
- Upload MTCP_paper_Abby_2026_v1_4_1_FINAL_updated.docx
- This gives the platform academic credibility — investors will check the DOI

**3. Test PDF certificate download**
- Go to /certificate on live site
- Each cert should have a download button
- If not working, check certificate_pdf.py is in the repo and reportlab is in requirements.txt

### 🟡 This Week

**4. Domain name**
- Register controlplane3.io or mtcp.ai on cloudflare.com/registrar (~$10/year)
- Add CNAME record: @ → control-plane-3.onrender.com
- Update landing page footer URL once domain is live

**5. GPT-4o benchmark**
- Add OpenAI API key to .env: `OPENAI_API_KEY=sk-...`
- Run: `python3 llm_safety_platform.py --data probes_200.json --api openai --models gpt-4o --temperature 0.0 --runs 1`
- Costs ~$0.50, adds huge credibility for enterprise buyers

**6. Fix leaderboard to pull from PostgreSQL**
- The leaderboard route aggregates by model+temperature
- Verify it's showing all 16 runs correctly on live site
- If showing "No data" check Render logs for psycopg2 errors

**7. Password change UI**
- Admin panel has a change password form
- Verify it works on live site
- If broken, check admin route in api_server.py handles POST to /admin/change-password

### 🟢 Next Week

**8. Multi-tenant architecture**
- Add org_id to users, runs, results tables in Neon
- Each customer sees only their own data
- Admin sees all orgs
- This is the SaaS foundation

**9. Role-based access**
- admin: full access
- enterprise: run benchmarks, see own results
- investor: read-only leaderboard (no raw data)

**10. Scheduled benchmark runs**
- /schedule endpoint for weekly automated re-runs
- Sell as "continuous compliance monitoring"
- Use APScheduler (compatible with FastAPI)

**11. Webhook/Slack alerts**
- Fire webhook when model score drops below threshold
- Enterprise CI/CD integration

**12. Demographic Consistency (DC) vector**
- 25 probes testing constraint persistence across demographic groups
- Directly addresses EU AI Act non-discrimination requirements

---

## COMMERCIAL STRATEGY

**Target valuation:** £5-10M
**EU AI Act deadline:** August 2026 — enterprise buyers actively purchasing NOW

**First outreach targets:**
- Credo AI (credo.ai) — enterprise AI governance
- Holistic AI (holisticai.com) — London, EU AI Act focus
- Arthur AI (arthur.ai) — model monitoring
- Anthropic — they will want to know their models scored D
- Meta AI — LLaMA results are good, may want to promote
- UK AI Safety Institute

**Outreach approach:** Send research summary with DOI first. Do NOT cold pitch.
Subject: "Independent MTCP evaluation — open source models outperform Claude on safety constraints"

**Pricing:**
- Free tier: run 1 benchmark, see leaderboard
- Professional £499/month: unlimited runs, all vectors, CSV export
- Enterprise £1999/month: multi-model, API access, certificates, scheduled runs
- Custom: white-label licensing

**IP protection:**
- probes_200.json must NEVER be made public — it is the crown jewel
- Platform code can be open source
- Consider provisional patent on MTCP protocol (£200 via UK IPO)

---

## RENDER ENVIRONMENT VARIABLES

| Key | Value |
|---|---|
| GROQ_API_KEY | gsk_... (set) |
| ANTHROPIC_API_KEY | sk-ant-... (set) |
| SECRET_KEY | [permanent value set] |
| DATABASE_URL | postgresql://neondb_owner:...@ep-sweet-art-al0epskk-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require |

---

## NEON DATABASE

- Project: control-plane-3
- Region: EU Central (Frankfurt)
- Branch ID: br-solitary-queen-aluj8446
- Free tier: 0.5GB storage, no expiry

---

## RUNNING BENCHMARKS

```bash
cd ~/Downloads/cp3
export $(cat .env | xargs)

# Groq (LLaMA)
python3 llm_safety_platform.py --data probes_200.json --api groq --models llama-3.1-8b-instant,llama-3.3-70b-versatile --temperature 0.0,0.2,0.5,0.8 --runs 1

# Anthropic (Claude)
python3 llm_safety_platform.py --data probes_200.json --api anthropic --models claude-haiku-4-5-20251001,claude-sonnet-4-20250514 --temperature 0.0 --runs 1
```

**Working models (March 2026):**
- llama-3.1-8b-instant ✅
- llama-3.3-70b-versatile ✅
- claude-haiku-4-5-20251001 ✅
- claude-sonnet-4-20250514 ✅

**Deprecated — DO NOT USE:**
- mixtral-8x7b-32768 ❌
- llama3-8b-8192 ❌
- gemma-7b-it ❌

---

## GITHUB

```bash
cd ~/Downloads/cp3
git add .
git commit -m "your message"
git push origin main --force
```

Render auto-deploys on every push to main.

---

## IMPORTANT NOTES FOR THE LLM

1. User is non-technical — plain English first, then exact commands ONE AT A TIME
2. Never chain multiple commands with && unless absolutely necessary
3. Python 3.9 — use Optional[] not | syntax
4. Database is now PostgreSQL/Neon — do NOT revert to SQLite for production
5. Load .env before every benchmark: `export $(cat .env | xargs)`
6. Keep server in one terminal, other work in another
7. All work in ~/Downloads/cp3/
8. GitHub is PRIVATE — push with --force
9. Never expose full probe methodology publicly
10. Research name is A. Abby — never use full name publicly
11. DOI already registered — always include in papers and certificates
12. Render auto-deploys when you push to GitHub main branch
13. If terminal gets stuck, press Ctrl+C or open a fresh terminal window
14. backup is at ~/Downloads/controlplane3_backup/
15. Neon free tier does NOT expire (unlike Render free PostgreSQL which expires in 30 days)

---
END OF HANDOFF PROMPT v3
