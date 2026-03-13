"""
evidence_scorer.py — T1: Evidence strength, direction, and composite scoring.

Converts extracted evidence items into numeric scores for T1 pass/fail.
Three independent sub-scores:
  - Evidence score: strength and volume of supporting literature
  - Mechanistic score: coherence of drug mechanism with disease pathway
  - Safety score: absence of disqualifying adverse event signals
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Strength → numeric weight
_STRENGTH_WEIGHTS = {"strong": 1.0, "moderate": 0.6, "weak": 0.3, "conflicting": -0.2}
# Direction → multiplier
_DIRECTION_MULT = {"supporting": 1.0, "neutral": 0.1, "opposing": -1.0}
# Evidence type → credibility weight
_TYPE_WEIGHTS = {
    "clinical": 1.0,
    "epidemiological": 0.85,
    "preclinical": 0.5,
    "mechanistic": 0.4,
    "genetic": 0.7,
    "transcriptomic": 0.6,
    "unknown": 0.2,
}


def score_evidence(
    evidence_items: list[dict],
    pathway_overlap: dict,
    polypharmacology: dict,
    ae_profile: dict,
) -> tuple[float, float, float]:
    """
    Compute three composite scores for T1 pass/fail.

    Args:
        evidence_items: list of structured evidence items from evidence_extractor
        pathway_overlap: dict from pathway_analyzer
        polypharmacology: dict from polypharmacology_scorer
        ae_profile: dict from faers_miner

    Returns:
        (evidence_score, mechanistic_score, safety_score) each in [0, 1]
    """
    evidence_score = _compute_evidence_score(evidence_items)
    mechanistic_score = _compute_mechanistic_score(pathway_overlap, polypharmacology)
    safety_score = _compute_safety_score(ae_profile)

    return (
        round(evidence_score, 4),
        round(mechanistic_score, 4),
        round(safety_score, 4),
    )


def _compute_evidence_score(items: list[dict]) -> float:
    """
    Weighted sum of evidence strength × direction × type credibility,
    normalized to [0, 1].

    More items and higher quality items → higher score.
    """
    if not items:
        return 0.0

    total = 0.0
    for item in items:
        strength = item.get("strength", "weak")
        direction = item.get("direction", "neutral")
        ev_type = item.get("evidence_type", "unknown")

        w = _STRENGTH_WEIGHTS.get(strength, 0.0)
        m = _DIRECTION_MULT.get(direction, 0.0)
        t = _TYPE_WEIGHTS.get(ev_type, 0.2)

        total += w * m * t

    # Normalize: max theoretical per item = 1.0 × 1.0 × 1.0 = 1.0
    # We cap at some reasonable max (e.g. 5 strong clinical supporting papers = 5.0 → normalized to 1.0)
    max_theoretical = max(len(items), 5)
    raw = total / max_theoretical
    return max(0.0, min(1.0, raw))


def _compute_mechanistic_score(pathway_overlap: dict, polypharmacology: dict) -> float:
    """
    Mechanistic coherence score combining:
      - Pathway overlap depth (shared pathways between drug targets and disease)
      - Synergistic polypharmacology score
    """
    overlap_n = pathway_overlap.get("overlap_n", 0)
    synergy = polypharmacology.get("synergy_score", 0.0)

    # Pathway overlap contribution: log-scaled, cap at 5 shared pathways = 1.0
    import math
    pathway_contrib = min(1.0, math.log1p(overlap_n) / math.log1p(5))

    # Synergy contribution
    synergy_contrib = float(synergy)

    # Weighted combination
    score = 0.65 * pathway_contrib + 0.35 * synergy_contrib
    return max(0.0, min(1.0, score))


def _compute_safety_score(ae_profile: dict) -> float:
    """
    Safety score: 1 - overall_ae_risk, with penalty for high-concern AEs.

    Higher score = safer profile for repurposing.
    """
    overall_risk = ae_profile.get("overall_ae_risk", 0.5)
    n_high_concern = len(ae_profile.get("high_concern_aes", []))

    # Hard penalty for high-concern AEs (cardiac, liver failure, etc.)
    concern_penalty = min(0.4, n_high_concern * 0.1)

    score = 1.0 - overall_risk - concern_penalty
    return max(0.0, min(1.0, score))


def summarize_evidence_direction(items: list[dict]) -> dict:
    """Return count breakdown of supporting/opposing/neutral evidence items."""
    counts = {"supporting": 0, "opposing": 0, "neutral": 0, "total": len(items)}
    for item in items:
        direction = item.get("direction", "neutral")
        counts[direction] = counts.get(direction, 0) + 1
    return counts
