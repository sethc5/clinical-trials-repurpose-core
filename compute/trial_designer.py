"""
trial_designer.py — T2: Phase II trial design generation.

Generates a structured Phase II trial design recommendation based on:
- Drug's known safety and PK profile
- Target indication's standard endpoints and regulatory precedent
- Biomarker-selected patient population (from biomarker_identifier)
- Dose range (from dose_analyzer)

Output format is designed to be actionable for a clinical team.
"""

from __future__ import annotations

import json
import logging

import llm_client

log = logging.getLogger(__name__)

TRIAL_DESIGN_PROMPT = """You are designing a Phase II clinical trial for a drug repurposing candidate.

Drug: {drug_name}
Target Indication: {indication_name}
Mechanism: {mechanism}
Proposed Dose: {proposed_dose}
Biomarkers for Patient Selection: {biomarkers}
Safety Profile: {safety_summary}
Target Population: {population}

Design a Phase II trial as structured JSON:
{{
  "trial_phase": "Phase 2",
  "design_type": "<randomized_controlled|single_arm|crossover|adaptive>",
  "primary_endpoint": {{
    "endpoint": "endpoint description",
    "timepoint": "measurement timepoint",
    "statistical_threshold": "e.g., p<0.05, HR<0.7"
  }},
  "secondary_endpoints": ["endpoint 1", "endpoint 2", "endpoint 3"],
  "sample_size": {{
    "n": <estimated sample size>,
    "power": 0.8,
    "alpha": 0.05,
    "rationale": "brief justification"
  }},
  "inclusion_criteria": ["criterion 1", "criterion 2"],
  "exclusion_criteria": ["criterion 1", "criterion 2"],
  "duration_months": <estimated trial duration>,
  "biomarker_enrichment": {{
    "enrichment_strategy": "description",
    "biomarker_threshold": "proposed threshold"
  }},
  "control_arm": "<placebo|standard_of_care|open_label>",
  "blinding": "<double_blind|single_blind|open_label>",
  "key_risks": ["risk 1", "risk 2"],
  "regulatory_considerations": "brief note on regulatory path"
}}

Only return JSON.
"""


def design_trial(
    drug: dict,
    indication: dict,
    target,  # TargetConfig
    model: str = "claude-opus-4-20250514",
    biomarkers: list | None = None,
    dose_rationale: dict | None = None,
) -> dict:
    """
    Generate a structured Phase II trial design for a T2 repurposing candidate.
    """
    drug_name = drug.get("name") or drug.get("drug_id")
    indication_name = indication.get("name") or indication.get("indication_id")
    mechanism = (drug.get("mechanism_of_action") or "unknown")[:300]

    proposed_dose = "See dose analysis"
    if dose_rationale and isinstance(dose_rationale, dict):
        proposed_dose = dose_rationale.get("proposed_dose", proposed_dose)

    biomarker_list = ""
    if biomarkers:
        biomarker_list = "; ".join(
            b.get("biomarker", "") for b in biomarkers[:3] if isinstance(b, dict)
        )

    # Safety summary from black box warnings
    bbw = drug.get("black_box_warnings") or []
    if isinstance(bbw, str):
        try:
            bbw = json.loads(bbw)
        except Exception:
            bbw = [bbw]
    safety_summary = f"BBW: {'; '.join(str(w) for w in bbw[:3])}" if bbw else "No black box warnings"

    # Population from target config
    pop_context = getattr(target, "population_context", None)
    population = str(pop_context) if pop_context else "General adult population"

    prompt = TRIAL_DESIGN_PROMPT.format(
        drug_name=drug_name,
        indication_name=indication_name,
        mechanism=mechanism,
        proposed_dose=proposed_dose,
        biomarkers=biomarker_list or "No specific biomarkers identified",
        safety_summary=safety_summary,
        population=population,
    )

    try:
        return llm_client.complete_json(prompt, model=model)
    except json.JSONDecodeError as e:
        log.warning(f"Trial design JSON parse failed: {e}")
        return {}
    except Exception as e:
        log.error(f"Trial design failed: {e}")
        return {}
