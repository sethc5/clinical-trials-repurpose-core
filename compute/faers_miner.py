"""
faers_miner.py — T1: FDA Adverse Event Reporting System signal mining.

Uses disproportionality analysis (Reporting Odds Ratio) to identify
which adverse events are statistically enriched for a drug.

Filters for AEs relevant to the target indication context:
  - AEs overlapping with indication disease pathology
  - AEs in the target population's contraindication list
  - Serious AEs that would preclude use in the indication
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# AEs that automatically increase concern regardless of indication
HIGH_CONCERN_AE_TERMS = frozenset([
    "cardiac arrest", "myocardial infarction", "stroke", "sudden death",
    "liver failure", "hepatic failure", "Stevens-Johnson", "toxic epidermal",
    "anaphylaxis", "QT prolongation", "torsade de pointes",
    "aplastic anemia", "agranulocytosis",
])


def mine_adverse_events(drug_id: str, indication: dict) -> dict:
    """
    Mine FAERS for adverse events relevant to the repurposing indication context.

    Returns:
        {
            "top_aes": [{ae_term, case_count, ror, significant}],
            "indication_relevant_aes": [...],
            "high_concern_aes": [...],
            "overall_ae_risk": float,  # 0-1, higher = more concerning
        }
    """
    from adapters.faers_adapter import FAERSAdapter
    from db_utils import RepurposingDB

    faers = FAERSAdapter()

    # Get drug name for FAERS lookup
    drug_name = drug_id  # fallback to ID; should be resolved by caller

    # Fetch top AEs
    ae_counts = faers.get_ae_counts(drug_name, limit=50)
    total_drug_reports = faers.get_total_reports_for_drug(drug_name)

    top_aes = []
    high_concern = []

    for ae in ae_counts[:50]:
        term = ae.get("term", "")
        count = ae.get("count", 0)

        ror_result = faers.compute_ror(drug_name, term, total_drug_reports)

        ae_record = {
            "ae_term": term,
            "case_count": count,
            "ror": ror_result.ror if ror_result else None,
            "ror_lower_ci": ror_result.ror_lower if ror_result else None,
            "significant": ror_result.significant if ror_result else False,
        }
        top_aes.append(ae_record)

        if any(concern.lower() in term.lower() for concern in HIGH_CONCERN_AE_TERMS):
            high_concern.append(ae_record)

    # Filter for indication-relevant AEs
    indication_relevant = _filter_indication_relevant(top_aes, indication)

    # Overall risk score: proportion of significant AEs + high-concern AE boost
    n_significant = sum(1 for ae in top_aes if ae.get("significant"))
    overall_risk = min(1.0, n_significant / max(len(top_aes), 1) + 0.2 * len(high_concern))

    return {
        "total_drug_reports": total_drug_reports,
        "top_aes": top_aes[:20],
        "indication_relevant_aes": indication_relevant[:10],
        "high_concern_aes": high_concern,
        "overall_ae_risk": round(overall_risk, 3),
    }


def _filter_indication_relevant(aes: list[dict], indication: dict) -> list[dict]:
    """Return AEs that are relevant to the indication's disease context."""
    indication_name = (indication.get("name") or "").lower()
    icd = (indication.get("icd10_code") or "").lower()

    relevant = []
    for ae in aes:
        term = (ae.get("ae_term") or "").lower()
        # Simple keyword relevance: AE term overlaps with indication name words
        indication_words = {w for w in indication_name.split() if len(w) > 4}
        if indication_words & set(term.split()):
            relevant.append(ae)

    return relevant
