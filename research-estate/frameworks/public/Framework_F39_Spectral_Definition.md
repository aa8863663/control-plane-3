# Spectral Constraint Displacement: Formal Definition and Specification

## Framework File F39 -- Version 1.0

**Issued by:** MTCP Research Programme  
**Author:** A. Abby  
**Date:** May 2026  
**DOI (methodology series):** 10.17605/OSF.IO/DXGK5  

---

## 1. Purpose

Prior frameworks measure constraint persistence outcomes (BIS, RES, ACPS) and classify failure types (architectural versus stochastic). No framework identifies the geometric mechanism producing those outcomes. Framework F39 defines Spectral Constraint Displacement as the mechanistic layer connecting SpectralQuant eigenvalue concentration findings to MTCP empirical measurements.

This framework provides:
- A causal mechanism for constraint persistence failure
- A geometric interpretation for BIS, RES, and temperature sensitivity
- A formal explanation for SAFETY_V1_033 (universal authority vulnerability)
- A connection between the three MTCP performance regimes and spectral properties

---

## 2. Background

SpectralQuant (Gopinath, 2026) establishes that transformer attention key vectors concentrate signal in approximately 4 effective dimensions out of 128 (d_eff/d = 3 to 4 percent). This is measured across six models in four architecture families. The property is universal and architecture-level.

MTCP independently measures constraint persistence failure patterns across 32 models and 183,924 evaluations. ARCS classifies those failures by temperature invariance and correction resistance.

Framework F39 connects cause (spectral concentration) to consequence (constraint failure patterns).

---

## 3. Formal Definitions

**Definition 1: Spectral Constraint Displacement.** The geometric mechanism by which a constraint signal is displaced from the effective key dimensions of transformer attention heads by a competing signal with higher eigenvalue coherence. Displacement is a step function. The constraint signal either maintains dominance in the effective dimensions or it does not.

**Definition 2: Effective Key Dimensions.** The d_eff dimensional subspace of each attention head key space that carries semantic signal. Determined by the participation ratio of the key vector covariance matrix. Empirically d_eff is approximately 4 on 128-dimensional heads across all tested architectures.

**Definition 3: Eigenvalue Coherence Score (ECS).** A measure of how much eigenvalue concentration a given signal generates in the effective key dimensions. Formally: ECS(signal) = PR(projection of signal onto effective subspace) weighted by alignment with the leading eigenvectors. High ECS indicates the signal generates concentrated activation in the effective dimensions.

**Definition 4: Noise Dimension.** Any dimension outside the d_eff effective subspace. Noise dimensions carry no semantic signal and do not influence attention patterns. Corrections applied to noise dimensions inject variance without restoring constraint signal.

**Definition 5: Spectral Dominance.** The state in which a constraint signal has higher eigenvalue coherence in the effective dimensions than any competing signal in the current context. BIS measures the proportion of interactions where spectral dominance is maintained.

---

## 4. The Spectral Displacement Lemma

A constraint C persists across turn t if and only if ECS(C) exceeds ECS(X) for all competing signals X in turn t, measured in the effective key dimensions.

**Corollary 1 (Hard Stop Condition).** A hard stop occurs when a competing signal achieves permanent spectral dominance that no subsequent correction sequence can reverse.

**Corollary 2 (Noise Dimension Correction Paradox).** A correction sequence with ECS lower than the displacing signal and significant noise-dimension activation will produce negative RES. The correction adds noise without restoring dominance.

**Corollary 3 (Temperature Invariance Prediction).** Displacement occurring in the effective dimensions is temperature-invariant because the eigenbasis is fixed by architecture. Temperature affects noise dimensions only.

---

## 5. Grading Scale Interpretation

The MTCP grading scale maps to spectral dominance maintenance:

| Grade | BIS Range | Spectral Interpretation |
|-------|-----------|------------------------|
| A | 90 to 100 | Constraint maintains spectral dominance in 90+ percent of interactions |
| B | 80 to 89 | Dominance maintained with occasional displacement under high-coherence attacks |
| C | 70 to 79 | Moderate displacement vulnerability, stochastic regime |
| D | 60 to 69 | Frequent displacement, weak eigenvalue allocation to constraints |
| F | Below 60 | Constraint signal does not achieve reliable dominance |

---

## 6. Classification of Failure Types

**Type 1: Architectural Displacement.** Displacement occurs in the effective dimensions by a signal with permanently higher eigenvalue coherence. Temperature-invariant. Correction-resistant. Corresponds to MTCP architectural classification.

**Type 2: Stochastic Displacement.** Displacement occurs at the boundary between effective and noise dimensions. Temperature-sensitive because noise-floor changes affect the margin. Correctable when noise is reduced. Corresponds to MTCP stochastic classification.

**Type 3: Coherence-Mediated Displacement.** Displacement by specific signal structures that generate unusually high eigenvalue coherence. Model-specific vulnerability where certain input patterns achieve displacement that other patterns do not. Corresponds to SAFETY_V1_033 universal authority vulnerability.

---

## 7. Measurement Protocol

**Minimum Requirements:**
- Per-head eigenspectral calibration data (d_eff, eigenvalues, eigenvectors)
- MTCP probe interaction data with per-turn constraint persistence labels
- Temperature sweep data for architectural versus stochastic classification

**Protocol Steps:**
1. Compute d_eff per head per layer via participation ratio
2. Identify effective subspace eigenvectors
3. Project constraint instructions and competing signals into effective subspace
4. Compute eigenvalue coherence scores for each signal type
5. Correlate ECS differential with constraint persistence outcomes
6. Classify displacement type by temperature sensitivity

**Controls:**
- Calibration stability (CV below 5 percent across data splits)
- Spectral gap ratio above 1.1 confirming clean signal-noise separation
- Multiple-seed evaluation confirming displacement is deterministic

---

## 8. Formal Properties

**P1 (Universality).** Spectral displacement operates identically across all architectures that exhibit d_eff/d approximately 3 to 4 percent. The mechanism is architecture-independent.

**P2 (Step Function).** Displacement is discrete. Partial displacement does not exist. The constraint either maintains dominance or it does not.

**P3 (Eigenvalue Ordering).** Displacement probability is monotonically related to the ECS differential between competing signal and constraint signal.

**P4 (Dimensional Boundedness).** Constraint capacity is bounded by d_eff. No operational intervention increases d_eff. Only architectural changes can increase effective dimensionality.

**P5 (Noise Paradox).** Corrections applied to noise dimensions have expected negative RES. This is a theorem not an observation. The mathematics are identical to SpectralQuant selective QJL analysis.

---

## 9. Relationship to Existing Constructs

- **BIS (F4):** Spectral dominance maintenance rate. BIS measures the empirical outcome of the displacement mechanism.
- **RES (F25):** Correctable only when intervention achieves ECS above the displacing signal in the effective dimensions. Negative RES predicted by noise dimension correction.
- **ACPS (F27):** Adversarial attacks that achieve displacement via high eigenvalue coherence signals.
- **Temperature Taxonomy (F6):** Temperature-invariant failures are effective-dimension displacements. Temperature-sensitive failures involve noise-dimension interference.
- **Persistence Lemma (Paper 9):** Spectral Displacement Lemma is the geometric extension.
- **IGS (Paper II):** Identity Gate Satiation is spectral saturation of effective dimensions by a competing identity signal.

---

## 10. Version Notes

**Version 1.0 (May 2026).** Initial formal definition. Based on SpectralQuant empirical findings and MTCP/ARCS correlation. Eigenvalue coherence scoring is theoretical. Empirical validation of ECS metric pending.

**Planned for Version 2.0:**
- Empirical ECS measurement protocol with calibration data
- Per-model spectral dominance profiles
- Cross-lingual eigenspectral analysis connecting to ARCS script distance findings
- Formal bounds on constraint capacity given d_eff

---

## 11. Public Status

Framework F39 is public. Full specification available. Empirical validation of ECS metric pending integration with SpectralQuant calibration pipeline.

---

## 12. References

Abby, A. (2026). Multi-Turn Constraint Persistence: Formal Framework. DOI: 10.17605/OSF.IO/DXGK5.  
Abby, A. (2026). ARCS: Architectural Risk and Constraint Safety. DOI: 10.17605/OSF.IO/7P5MK.  
Abby, A. (2026). MTCP Paper 32: Remediation Effectiveness Score. DOI: 10.17605/OSF.IO/DXGK5.  
Abby, A. (2026). MTCP Paper 49: Spectral Constraint Displacement. DOI: 10.17605/OSF.IO/DXGK5.  
Gopinath, A. (2026). SpectralQuant: 3% Is All You Need. NeurIPS 2026 submission.  
Zandieh, A. et al. (2026). TurboQuant. ICLR 2026.  

*Framework F39 -- Created May 2026. Defines the geometric mechanism of constraint persistence failure as spectral displacement in the effective key dimensions of transformer attention heads.*
