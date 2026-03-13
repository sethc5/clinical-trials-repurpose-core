"""
failed_trial_classifier.py — T0.25: Classify trial failures by root cause.

Categorizes ClinicalTrials.gov termination reasons into structured classes
so the pipeline can distinguish drug failures from indication/dose/population failures.

Key insight: Only clean mechanism failures (drug doesn't do what biology predicts)
are disqualifying. All other failures are potential repurposing opportunities.

Failure categories:
  - 'efficacy': drug mechanism failed — genuine negative result
  - 'dose': wrong dose for this indication — rescuable
  - 'population': wrong patient population — rescuable with biomarker selection
  - 'commercial': sponsor decision, underfunding, market size — biology is fine
  - 'safety_in_population': AE in specific population — may be safe in different population
  - 'enrollment': failed to recruit — no efficacy data, not disqualifying
  - 'unknown': cannot classify
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Keyword patterns per failure category
_PATTERNS = {
    "efficacy": [
        r"lack of efficacy",  r"no efficacy", r"insufficient efficacy",
        r"primary endpoint not met", r"futility", r"no significant",
        r"failed to demonstrate", r"no effect", r"ineffective",
    ],
    "dose": [
        r"dose", r"dosage", r"concentration", r"exposure", r"subtherapeutic",
        r"overdose", r"drug level", r"pharmacokinetic",
    ],
    "population": [
        r"patient population", r"inclusion criteria", r"exclusion criteria",
        r"subgroup", r"biomarker", r"stratif", r"wrong population",
        r"off target", r"unselected",
    ],
    "commercial": [
        r"business", r"commercial", r"financial", r"funding", r"budget",
        r"sponsor decision", r"strategic", r"company", r"market",
        r"portfolio", r"resource",
    ],
    "safety_in_population": [
        r"safety concern", r"adverse event", r"toxicity", r"side effect",
        r"risk\-benefit", r"serious adverse", r"mortality",
    ],
    "enrollment": [
        r"enrollment", r"recruitment", r"accrual", r"enroll",
        r"insufficient patient", r"low enrollment",
    ],
}

_COMPILED = {
    cat: [re.compile(pat, re.IGNORECASE) for pat in patterns]
    for cat, patterns in _PATTERNS.items()
}


def classify_termination_reason(reason_text: str) -> str:
    """
    Classify a ClinicalTrials.gov termination reason string into a category.

    Returns one of: 'efficacy', 'dose', 'population', 'commercial',
                    'safety_in_population', 'enrollment', 'unknown'
    """
    if not reason_text:
        return "unknown"

    scores: dict[str, int] = {cat: 0 for cat in _COMPILED}
    for cat, patterns in _COMPILED.items():
        for pat in patterns:
            if pat.search(reason_text):
                scores[cat] += 1

    # Return category with highest match count; 'unknown' if no matches
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "unknown"


def classify_failed_trials(
    drug_id: str,
    indication_id: str,
    db,  # RepurposingDB
) -> dict:
    """
    Check whether a drug-indication pair has prior trial failures,
    and if so, classify the failure reason.

    Returns:
        {
            "failed": bool,
            "trial_id": str | None,
            "phase": str | None,
            "failure_category": str | None,   # 'efficacy', 'dose', etc.
            "is_rescuable": bool,              # True if failure was not mechanism-level
        }
    """
    trials = db.get_trials_for_pair(drug_id, indication_id)

    for trial in trials:
        status = (trial.get("status") or "").upper()
        success = trial.get("success")
        reason = trial.get("termination_reason") or ""

        is_completed_negative = (
            status in ("COMPLETED", "TERMINATED")
            and success is False
        )

        if is_completed_negative:
            category = classify_termination_reason(reason)
            is_rescuable = category != "efficacy"
            return {
                "failed": True,
                "trial_id": trial.get("trial_id"),
                "phase": trial.get("phase"),
                "failure_category": category,
                "failure_reason": reason,
                "is_rescuable": is_rescuable,
            }

    return {
        "failed": False,
        "trial_id": None,
        "phase": None,
        "failure_category": None,
        "failure_reason": None,
        "is_rescuable": True,
    }
