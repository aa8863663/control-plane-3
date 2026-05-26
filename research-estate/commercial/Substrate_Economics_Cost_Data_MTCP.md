# Substrate Economics: MTCP Runtime Inference Cost Data

A. Abby
admin@mtcp.live
DOI: 10.17605/OSF.IO/DXGK5
May 2026

---

## 1. Executive Summary

Runtime governance evaluation costs range from $0.082 to $1.88 per BIS evaluation depending on provider tier. A full-stack evaluation (BIS plus CSAS plus ACPS) costs $0.43 to $9.80 per decision. At Health System scale (1 million decisions per day) the annual full-stack inference cost ranges from $156 million (cheapest provider) to $3.58 billion (most expensive provider). The average re-run multiplier across all models is 1.36x due to temperature-induced variance in 13 of 35 models.

---

## 2. Per Evaluation Type Cost Table

### 2.1 BIS Evaluation

The BIS evaluation follows the standard MTCP three-turn protocol. Turn 1 delivers the constraint instruction and receives the model response. Turn 2 applies correction pressure. Turn 3 assesses final compliance. Total token consumption is approximately 850 tokens per evaluation.

Input tokens per evaluation: 350. Output tokens per evaluation: 500. Total tokens: 850.

Cost at Nova Micro tier (floor): $0.08225 per evaluation. Cost at Nova Pro tier (ceiling): $1.88000 per evaluation. Cost per million evaluations at floor: $82,250. Cost per million evaluations at ceiling: $1,880,000.

Nova Lite tier costs $0.141 per evaluation. Mistral Large tier costs $1.48 per evaluation. OpenRouter midpoint estimate costs $0.925 per evaluation.

### 2.2 CSAS Evaluation

CSAS evaluates constraint persistence across two coordinated models. Each model runs the three-turn protocol independently. Token consumption is approximately double a single BIS evaluation. Total tokens per CSAS evaluation: 1,700.

Input tokens per evaluation: 700. Output tokens per evaluation: 1,000.

Cost at Nova Micro tier (floor): $0.1645 per evaluation. Cost at Nova Pro tier (ceiling): $3.76 per evaluation. Cost per million evaluations at floor: $164,500. Cost per million evaluations at ceiling: $3,760,000.

### 2.3 ACPS Evaluation

ACPS evaluates constraint persistence under four adversarial attack types. Each attack type requires a structured adversarial prompt longer than standard BIS probes. Total tokens per ACPS evaluation: 2,200.

Input tokens per evaluation: 1,200. Output tokens per evaluation: 1,000.

Cost at Nova Micro tier (floor): $0.182 per evaluation. Cost at Nova Pro tier (ceiling): $4.16 per evaluation. Cost per million evaluations at floor: $182,000. Cost per million evaluations at ceiling: $4,160,000.

### 2.4 Full Stack Per Decision

A complete runtime governance evaluation for one decision requires BIS plus CSAS plus ACPS. Total tokens per full-stack evaluation: 4,750.

Cost at floor (Nova Micro): $0.42875 per decision. Cost at ceiling (Nova Pro): $9.80 per decision.

---

## 3. Scale Point Cost Table

Five scale points represent increasing deployment contexts from pilot through sovereign infrastructure.

### Pilot: 2,400 decisions per day

BIS only daily cost: $197 (floor) to $4,512 (ceiling). Full stack daily cost: $1,029 (floor) to $23,520 (ceiling). Full stack annual cost: $375,585 (floor) to $8,584,800 (ceiling).

### Department: 10,000 decisions per day

BIS only daily cost: $823 (floor) to $18,800 (ceiling). Full stack daily cost: $4,288 (floor) to $98,000 (ceiling). Full stack annual cost: $1,564,938 (floor) to $35,770,000 (ceiling).

### Hospital: 100,000 decisions per day

BIS only daily cost: $8,225 (floor) to $188,000 (ceiling). Full stack daily cost: $42,875 (floor) to $980,000 (ceiling). Full stack annual cost: $15,649,375 (floor) to $357,700,000 (ceiling).

### Health System: 1,000,000 decisions per day

BIS only daily cost: $82,250 (floor) to $1,880,000 (ceiling). Full stack daily cost: $428,750 (floor) to $9,800,000 (ceiling). Full stack annual cost: $156,493,750 (floor) to $3,577,000,000 (ceiling).

### Sovereign Large: 10,000,000 decisions per day

BIS only daily cost: $822,500 (floor) to $18,800,000 (ceiling). Full stack daily cost: $4,287,500 (floor) to $98,000,000 (ceiling). Full stack annual cost: $1,564,937,500 (floor) to $35,770,000,000 (ceiling).

---

## 4. Variance Analysis

Variance measures the difference in pass rate between T=0.0 and T=0.8 for each model. High variance models require multiple re-runs to produce a defensible repeatable verdict. This adds a cost multiplier to the per-evaluation figure.

### 4.1 Deterministic-Equivalent Models

Twenty-two of 35 models show variance below 2 percent between T=0.0 and T=0.8. These models produce stable verdicts on a single run at any temperature. No re-run cost multiplier applies. The deterministic-equivalent set includes: cerebras-llama-8b, claude-haiku-4-5-20251001, command-a-03-2025, command-r7b, gemini-2.0-flash, gemini-2.5-flash, gemma-2-27b-it, gpt-3.5-turbo, gpt-4o, kimi-k2, llama-3.1-70b-instruct, llama-3.1-nemotron-70b-instruct, llama-3.3-70b-versatile, llama-4-maverick, llama-4-scout, magistral-medium-latest, ministral-8b, mistral-large, mistral-small-3.2, nova-lite, nova-micro, and qwen-2.5-7b.

### 4.2 Moderate Variance Models

Eleven models show variance between 2 and 10 percent. These require 1.5 to 2.0 re-runs for stable verdicts. The affected models include: claude-sonnet-4-5-20250929 (7.6 percent delta, 2.0x), qwen3-32b (9.1 percent, 2.0x), cohere-command-r-plus (4.8 percent, 1.5x), gpt-4o-mini (4.6 percent, 1.5x), granite-3.3-8b-instruct (4.5 percent, 1.5x), nova-pro (4.2 percent, 1.5x), phi-4-mini-instruct (4.1 percent, 1.5x), phi-4 (3.6 percent, 1.5x), gemma-3-27b-it (3.2 percent, 1.5x), grok-3-mini (2.6 percent, 1.5x), and llama-3.1-8b-instant (2.3 percent, 1.5x).

### 4.3 High Variance Models

Two models show variance above 10 percent. These require 3 to 5 re-runs for defensible verdicts. Qwen3-8b shows 34.9 percent delta between T=0.0 (50.4 percent pass) and T=0.8 (85.3 percent pass). This requires a 5.0x cost multiplier. DeepSeek-R1 shows 17.3 percent delta. This requires a 3.0x cost multiplier.

### 4.4 Effective Cost with Re-Run Multiplier

The average re-run multiplier across all 35 models is 1.36x. Applying this to the per-evaluation costs: effective BIS cost at floor is $0.112 per evaluation. Effective full-stack cost at floor is $0.583 per evaluation. At Health System scale the variance-adjusted annual full-stack cost at floor becomes $212,831,500.

---

## 5. Constitutional Layer Note

The MTCP governance stack includes 15 layers. Only three require per-decision runtime inference: BIS, CSAS, and ACPS. The remaining layers are design-time, periodic, or negligible-cost operations.

COS (Constraint Object Specification) is a design-time definition. It does not require inference. LRP (Legitimacy Resolution Protocol) is a design-time authority establishment. It does not require inference. GRC (Governance Reference Conditions) is a design-time comparability check. It does not require inference. DRA (Deployment Readiness Attestation) is a periodic composite assessment. It runs at deployment gates not per decision. TDS (Temporal Drift Score) is periodic. It runs on a schedule to detect drift. Not per decision.

BEC (Blockchain Evidence Chain) is a SHA-256 hash operation. Computational cost is negligible. No inference required. The Admissibility Gate is a threshold lookup against stored scores. No inference required.

The per-decision runtime inference cost is BIS plus CSAS plus ACPS only. All other layers contribute to the governance infrastructure but not to the per-decision inference budget.

---

## 6. Raw Data Summary

Total evaluations analysed: 181,448 BIS evaluation records from the consolidated MTCP dataset.

Models covered: 35 distinct models spanning instruction-tuned, open-weight, and proprietary architectures. Model sizes range from 8 billion to 70 billion parameters. Architectures include Llama, Qwen, Gemma, Mistral, Claude, GPT, Nova, Granite, DeepSeek, Cerebras, Cohere Command, Phi, Grok, and Kimi.

Providers covered: 14 distinct inference providers. Amazon Bedrock, Anthropic, Cerebras, Cohere, DeepSeek, Fireworks, GitHub, Google, Groq, Mistral, NVIDIA NIM, OpenAI, OpenRouter, and xAI.

Date range: March 2026 through May 2026.

CSAS and ACPS evaluation counts: CSAS and ACPS evaluations are computed from protocol specification rather than empirical token counts. The token estimates derive from the standard MTCP three-turn structure with appropriate multipliers for dual-model (CSAS) and four-attack-type (ACPS) protocols.

No actual token consumption data is stored in the evaluation database. All cost figures use protocol-based estimates validated against the standard probe structure of 150 input tokens and 200 output tokens per turn for BIS, doubled for CSAS, and 300 input plus 250 output per attack type for ACPS.

---

## Pricing Sources

Nova Micro: $0.035/1K input, $0.14/1K output (AWS Bedrock public pricing May 2026). Nova Lite: $0.06/1K input, $0.24/1K output. Nova Pro: $0.80/1K input, $3.20/1K output. Mistral Large: $0.80/1K input, $2.40/1K output (Mistral API pricing). OpenRouter midpoint: $0.50/1K input, $1.50/1K output (conservative estimate across OpenRouter model catalogue).

---

## Document Status

This document is input data for the substrate economics joint paper with Axius SDC. Not for distribution without review. Cost figures are estimates based on protocol token consumption and public pricing. Actual costs will vary by volume discounts, reserved capacity, and provider-specific agreements.
