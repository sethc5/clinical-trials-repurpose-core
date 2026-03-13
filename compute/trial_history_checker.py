"""
trial_history_checker.py — T0: ClinicalTrials.gov lookup for prior attempts.

Determines whether a drug-indication pair has:
  1. An active trial (exclude from screening if so)
  2. Already been approved for this indication
  3. A prior Phase III failure (definitive negative)
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def check_trial_history(
    drug_id: str,
    indication_id: str,
    db,  # RepurposingDB
) -> bool:
    """
    Return True if this drug-indication pair is 'already tried' in the sense
    that should exclude it at T0.

    Excludes if:
      - Drug is already in active Phase II/III trials for this indication
      - Drug is already approved for this indication

    Does NOT exclude for prior failures (those are flagged at T0.25, not T0).
    """
    trials = db.get_trials_for_pair(drug_id, indication_id)

    for trial in trials:
        status = (trial.get("status") or "").upper()
        phase = (trial.get("phase") or "").upper()

        # Active trial for this exact indication — skip (already being investigated)
        if status in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION",
                      "NOT_YET_RECRUITING"):
            log.debug(f"{drug_id} × {indication_id}: active trial {trial.get('trial_id')}")
            return True

        # Drug already has Phase 4 / post-market for this indication = approved
        if status == "COMPLETED" and phase in ("PHASE4", "PHASE 4"):
            if trial.get("success") is True:
                log.debug(f"{drug_id} × {indication_id}: already approved (Phase 4 success)")
                return True

    return False


def check_definitive_phase3_failure(
    drug_id: str,
    indication_id: str,
    db,
    min_enrollment: int = 1000,
) -> bool:
    """
    Return True if there is a completed Phase III trial with:
      - enrollment >= min_enrollment
      - success = False
      - termination_reason indicates efficacy failure (not dose/population)

    These are definitive failures — the mechanism doesn't work for this indication.
    """
    trials = db.get_trials_for_pair(drug_id, indication_id)

    for trial in trials:
        phase = (trial.get("phase") or "").upper()
        status = (trial.get("status") or "").upper()
        enrollment = trial.get("enrollment") or 0
        success = trial.get("success")
        reason = (trial.get("termination_reason") or "").lower()

        if (
            "PHASE3" in phase.replace(" ", "")
            and status in ("COMPLETED", "TERMINATED")
            and success is False
            and enrollment >= min_enrollment
        ):
            # Only definitive if failure reason is efficacy, not dose/population/commercial
            efficacy_failure_words = ["efficacy", "no effect", "primary endpoint not met",
                                      "lack of efficacy", "futility"]
            rescue_words = ["enrollment", "commercial", "business", "sponsor decision",
                            "funding", "dose", "population", "safety"]
            is_efficacy = any(w in reason for w in efficacy_failure_words)
            is_rescuable = any(w in reason for w in rescue_words)

            if is_efficacy and not is_rescuable:
                log.debug(f"{drug_id} × {indication_id}: definitive Phase III failure")
                return True

    return False
