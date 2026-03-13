"""
safety_filter.py — T0: Black box warning and contraindication matching.

Checks drug safety profile against target population constraints.
Pure database lookup — no API calls, millisecond execution.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def check_safety_compatibility(
    drug: dict,
    indication: dict,
    target: Any,  # TargetConfig
    filter_config: Any,  # T0FilterConfig
) -> bool:
    """
    Return True if the drug's safety profile is compatible with the target indication.

    Checks:
      1. Black box warnings incompatible with target population
      2. Contraindications explicitly covering the target indication or population
      3. Safety exclusion classes defined in the target config
    """
    if not filter_config.exclude_black_box_for_population:
        return True

    drug_bbw = _parse_list(drug.get("black_box_warnings"))
    drug_contraindications = _parse_list(drug.get("contraindications"))

    # Get exclusion patterns from target config
    safety_exclusions = getattr(target, "safety_exclusions", []) or []
    population_context = getattr(target, "population_context", None)
    exclude_conditions = getattr(population_context, "exclude_conditions", []) if population_context else []

    # Check BBW against safety exclusion classes
    for exclusion in safety_exclusions:
        if _matches_any(exclusion.lower(), drug_bbw + drug_contraindications):
            log.debug(f"Drug {drug.get('drug_id')} excluded: safety exclusion '{exclusion}'")
            return False

    # Check explicit population contraindications
    for condition in exclude_conditions:
        if _matches_any(condition.lower(), drug_contraindications):
            log.debug(f"Drug {drug.get('drug_id')} excluded: contraindicated for '{condition}'")
            return False

    # Check pregnancy if target population constraints specify it
    pregnancy_cat = drug.get("pregnancy_category") or ""
    if "teratogenicity" in safety_exclusions and pregnancy_cat in ("X", "D"):
        return False

    return True


def check_black_box_for_indication(drug: dict, indication: dict) -> list[str]:
    """
    Return any black box warnings that are specifically relevant to the indication context.
    Returns empty list if none are relevant.
    """
    bbw = _parse_list(drug.get("black_box_warnings"))
    indication_terms = [
        indication.get("name", "").lower(),
        indication.get("mesh_id", "").lower(),
    ]
    relevant = []
    for warning in bbw:
        warning_lower = warning.lower()
        for term in indication_terms:
            if term and term in warning_lower:
                relevant.append(warning)
                break
    return relevant


def assess_narrow_therapeutic_index(drug: dict) -> bool:
    """
    Heuristic check for narrow therapeutic index drugs.
    These require extra caution for repurposing (dose-sensitive).
    """
    nti_keywords = [
        "narrow therapeutic", "therapeutic index", "warfarin", "digoxin",
        "lithium", "phenytoin", "theophylline", "aminoglycoside",
        "cyclosporine", "tacrolimus"
    ]
    moa = (drug.get("mechanism_of_action") or "").lower()
    name = (drug.get("name") or "").lower()
    generic = (drug.get("generic_name") or "").lower()
    text = f"{moa} {name} {generic}"
    return any(kw in text for kw in nti_keywords)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_list(field: Any) -> list[str]:
    if isinstance(field, list):
        return [str(x) for x in field]
    if isinstance(field, str):
        try:
            parsed = json.loads(field)
            return [str(x) for x in parsed] if isinstance(parsed, list) else [field]
        except Exception:
            return [field] if field else []
    return []


def _matches_any(pattern: str, text_list: list[str]) -> bool:
    """Return True if pattern appears in any text in text_list."""
    pattern_words = pattern.replace("_", " ").split()
    for text in text_list:
        text_lower = text.lower()
        if all(word in text_lower for word in pattern_words):
            return True
    return False
