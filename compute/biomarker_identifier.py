"""
biomarker_identifier.py — T2: Patient stratification biomarker extraction.

Identifies biomarkers that could be used to select patients most likely
to respond to the repurposed drug. Key for trial design and precision medicine.

Types of biomarkers:
  - Predictive: predicts response to treatment
  - Prognostic: predicts disease course regardless of treatment
  - Pharmacodynamic: tracks drug effect
  - Safety: identifies patients at risk of AEs
"""

from __future__ import annotations

import json
import logging

import llm_client

log = logging.getLogger(__name__)

BIOMARKER_PROMPT = """You are identifying patient stratification biomarkers for a drug repurposing clinical trial.

Drug: {drug_name}
Mechanism: {mechanism}
Target Indication: {indication_name}
Disease Genes: {disease_genes}
Drug Targets: {drug_targets}
Evidence Summary: {evidence_summary}

Identify 3-5 patient stratification biomarkers as JSON array:
[
  {{
    "biomarker": "name/test",
    "type": "<predictive|prognostic|pharmacodynamic|safety>",
    "rationale": "1-2 sentences explaining why this biomarker would enrich for responders",
    "measurement": "how to measure (e.g., blood test, tissue biopsy, imaging)",
    "threshold": "proposed enrichment threshold if known"
  }}
]

Focus on mechanistically justified biomarkers, not generic ones.
Only return the JSON array, no other text.
"""


def identify_biomarkers(
    drug: dict,
    indication: dict,
    model: str = "claude-opus-4-20250514",
    evidence_summary: str = "",
) -> list[dict]:
    """
    Extract candidate patient stratification biomarkers for a T2 repurposing pair.

    Returns list of biomarker dicts, or empty list if extraction fails.
    """
    drug_name = drug.get("name") or drug.get("drug_id")
    mechanism = (drug.get("mechanism_of_action") or "")[:400]
    indication_name = indication.get("name") or indication.get("indication_id")

    # Extract gene lists
    drug_targets = _extract_genes(drug.get("primary_targets") or [])
    disease_genes = _extract_genes(indication.get("disease_genes") or [])

    prompt = BIOMARKER_PROMPT.format(
        drug_name=drug_name,
        mechanism=mechanism,
        indication_name=indication_name,
        disease_genes=", ".join(disease_genes[:10]),
        drug_targets=", ".join(drug_targets[:5]),
        evidence_summary=(evidence_summary or "Not available.")[:500],
    )

    try:
        return llm_client.complete_json(prompt, model=model)
    except json.JSONDecodeError as e:
        log.warning(f"Biomarker JSON parse failed: {e}")
        return []
    except Exception as e:
        log.error(f"Biomarker identification failed: {e}")
        return []


def _extract_genes(targets: list) -> list[str]:
    genes = []
    for t in targets:
        if isinstance(t, dict):
            g = t.get("gene_name") or t.get("gene_symbol")
            if g:
                genes.append(g)
        elif isinstance(t, str):
            genes.append(t)
    return genes
