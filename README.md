# Control Plane 3

**Multi-Turn Constraint Persistence (MTCP) Evaluation Platform**

A black-box LLM safety evaluation framework measuring post-correction behavioral stability in frontier models.

**DOI:** https://doi.org/10.17605/OSF.IO/DXGK5
**Live Platform:** https://control-plane-3.onrender.com
**© 2026 A. Abby. All Rights Reserved.**

---

## Abstract

We introduce MTCP (Multi-Turn Constraint Persistence), a black-box evaluation framework measuring whether large language models maintain compliance with explicit constraints across structured correction sequences. Unlike existing benchmarks that evaluate single-turn instruction-following or adversarial jailbreak resistance, MTCP focuses on post-correction reliability: given that a model fails a constraint, can it be corrected, and does that correction hold?

We benchmark four frontier models across four sampling temperatures, yielding 16 evaluation runs. Key findings include: open-source models outperform paid commercial alternatives on constraint persistence; model families exhibit differential sensitivity to sampling temperature; and no tested model achieves a passing grade under MTCP, indicating an industry-wide gap in post-correction compliance.

The framework produces SHA-256 verified compliance certificates applicable to EU AI Act Annex IV technical documentation requirements.

Full methodology and dataset are available under NDA for research and commercial licensing.

---

## Access

This repository is **private**. Methodology, probe dataset, and platform are proprietary.

Research collaboration and commercial licensing enquiries:
https://control-plane-3.onrender.com/landing

