"""
competitive_landscape.py — T2: Competitive analysis for repurposing candidates.

Identifies who else is working on the same drug-indication space:
  - Other drugs in trials for the same indication with similar mechanism
  - Academic groups publishing in the space
  - Biotech/pharma programs (from ClinicalTrials + patent landscape)
  - FDA Orphan Drug designations (for rare diseases)
"""

from __future__ import annotations

import json
import logging

import llm_client

log = logging.getLogger(__name__)

LANDSCAPE_PROMPT = """You are conducting competitive intelligence for a drug repurposing program.

Drug: {drug_name}
Mechanism: {mechanism}
Target Indication: {indication_name}

Active Trials in Indication:
{active_trials}

Known Context:
{context}

Summarize the competitive landscape as JSON:
{{
  "n_active_trials_same_indication": <int>,
  "competing_drugs": [
    {{
      "drug": "drug name",
      "mechanism": "brief mechanism",
      "phase": "trial phase",
      "sponsor": "company/institution",
      "differentiation": "how our candidate differs"
    }}
  ],
  "key_academic_groups": ["group 1", "group 2"],
  "orphan_drug_designations": ["drug: indication"],
  "differentiation_strategy": "1-2 sentences on how this candidate is differentiated",
  "freedom_to_operate": "<clear|uncertain|limited>",
  "patent_risk": "brief note on IP considerations",
  "overall_competitive_assessment": "<favorable|neutral|challenging>"
}}

Only return JSON.
"""


def analyze_competitive_landscape(
    drug: dict,
    indication: dict,
    model: str = "claude-opus-4-20250514",
    db=None,
) -> dict:
    """
    Generate competitive landscape analysis for a T2 repurposing candidate.
    """
    drug_name = drug.get("name") or drug.get("drug_id")
    mechanism = (drug.get("mechanism_of_action") or "unknown")[:300]
    indication_name = indication.get("name") or indication.get("indication_id")

    # Get active trials for this indication (from DB if available)
    active_trials_text = "No trial data loaded in DB yet."
    if db:
        try:
            trials = db.get_trials_for_pair(drug.get("drug_id"), indication.get("indication_id"))
            active_trials_text = json.dumps(
                [{"trial_id": t.get("trial_id"), "status": t.get("status"),
                  "phase": t.get("phase"), "sponsor": t.get("sponsor")}
                 for t in trials[:10]],
                indent=2
            )
        except Exception:
            pass

    prompt = LANDSCAPE_PROMPT.format(
        drug_name=drug_name,
        mechanism=mechanism,
        indication_name=indication_name,
        active_trials=active_trials_text,
        context=f"Drug type: {drug.get('drug_type')}. Status: {drug.get('status')}.",
    )

    try:
        return llm_client.complete_json(prompt, model=model)
    except json.JSONDecodeError as e:
        log.warning(f"Competitive landscape JSON parse failed: {e}")
        return {}
    except Exception as e:
        log.error(f"Competitive landscape analysis failed: {e}")
        return {}
