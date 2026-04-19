# Control Plane 3

**Multi-Turn Constraint Persistence (MTCP) Evaluation Platform**

A black-box LLM safety evaluation framework measuring post-correction behavioral stability across 32 production models from 13 providers.

**DOI:** https://doi.org/10.17605/OSF.IO/DXGK5
**Live Platform:** https://mtcp.live
**© 2026 A. Abby. All Rights Reserved.**

---

## Abstract

We introduce MTCP (Multi-Turn Constraint Persistence), a black-box evaluation framework measuring whether large language models maintain compliance with explicit constraints across structured correction sequences. Unlike existing benchmarks that evaluate single-turn instruction-following or adversarial jailbreak resistance, MTCP focuses on post-correction reliability: given that a model fails a constraint, can it be corrected, and does that correction hold?

We benchmark 32 production models from 13 providers using 532 probes across multiple sampling temperatures, yielding 181,448 probe evaluations. Key findings include: no model achieves Grade A (90%+ threshold); the best performer (grok-3-mini) reaches 88.7% (Grade B); GPT-4o scores 16.2 percentage points below GPT-4o-mini demonstrating inverse scaling; safety-tuned models cluster at 66–68% with under 1pp temperature variance indicating architectural rather than stochastic failure; and open-source models outperform commercial alternatives on constraint persistence.

The framework produces SHA-256 verified compliance certificates applicable to EU AI Act Annex IV technical documentation requirements.

Full methodology and dataset are available under NDA for research and commercial licensing.

---

## Access

This repository is **private**. Methodology, probe dataset, and platform are proprietary.

Research collaboration and commercial licensing enquiries:
https://mtcp.live/landing

