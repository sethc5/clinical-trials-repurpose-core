"""
dose_analyzer.py — T2: Dose-response analysis for repurposing dose selection.

Key problem: A drug approved at dose X for indication A may work at dose Y
for indication B. The pipeline needs to identify the dose range that achieves
the target mechanism effect based on available PK/PD data.

Critical for longevity repurposing: rapamycin works at sub-immunosuppressive
doses for longevity via mTORC1 inhibition — very different from transplant dosing.
"""

from __future__ import annotations

import json
import logging
import math
import re

import llm_client
import pharma_formulas

log = logging.getLogger(__name__)

DOSE_PROMPT = """You are analyzing dose selection for a drug repurposing clinical trial.

Drug: {drug_name}
Approved Indication Dose: {approved_dose}
Mechanism of Action: {mechanism}
Target Indication: {indication_name}
Target Mechanism: {target_mechanism}

Evidence from literature: {dose_evidence}

Computed PK parameters (from structured database data — use these numbers, do not hallucinate PK constants):
{pk_computed}

Provide dose rationale as JSON:
{{
  "proposed_dose": "dose and schedule",
  "dose_rationale": "2-3 sentence mechanistic justification",
  "approved_dose_context": "how proposed dose compares to approved dose and why",
  "pk_considerations": "relevant PK factors (half-life, bioavailability, tissue penetration)",
  "safety_margin": "estimated margin between proposed dose and doses causing known toxicity",
  "dose_range_for_trial": {{
    "low": "low dose arm",
    "mid": "mid dose arm",
    "high": "high dose arm"
  }},
  "dose_finding_needed": <true if formal dose-finding Phase I needed first>,
  "confidence": "<low|moderate|high>"
}}

Only return JSON, no prose.
"""


def analyze_dose(
    drug: dict,
    indication: dict,
    model: str = "claude-opus-4-20250514",
) -> dict:
    """
    Generate dose selection rationale for a repurposing candidate.

    Returns a dict with proposed dose, rationale, and PK considerations.
    Returns empty dict if analysis fails.
    """
    drug_name = drug.get("name") or drug.get("drug_id")
    mechanism = (drug.get("mechanism_of_action") or "unknown")[:400]
    indication_name = indication.get("name") or indication.get("indication_id")
    approved_dose = _extract_approved_dose(drug)
    priority_mechanisms = getattr(indication, "priority_mechanisms", [])
    target_mechanism = ", ".join(priority_mechanisms[:3]) if isinstance(priority_mechanisms, list) else ""

    prompt = DOSE_PROMPT.format(
        drug_name=drug_name,
        approved_dose=approved_dose,
        mechanism=mechanism,
        indication_name=indication_name,
        target_mechanism=target_mechanism or "target mechanism not specified",
        dose_evidence="See literature evidence (not yet available in this stub).",
        pk_computed=_compute_pk_context(drug),
    )

    try:
        return llm_client.complete_json(prompt, model=model)
    except json.JSONDecodeError as e:
        log.warning(f"Dose analysis JSON parse failed: {e}")
        return {}
    except Exception as e:
        log.error(f"Dose analysis failed: {e}")
        return {}


def _compute_pk_context(drug: dict) -> str:
    """Build structured PK context using pharma_formulas where possible."""
    lines: list[str] = []

    # Molecular weight from formula (or stored mw)
    formula = drug.get("molecular_formula")
    mw = drug.get("mw")
    if formula:
        try:
            res = pharma_formulas.molar_mass(formula)
            lines.append(f"Molecular weight: {res.value:.1f} g/mol (formula: {formula})")
            mw = res.value
        except Exception:
            if mw:
                lines.append(f"Molecular weight: {mw:.1f} Da")
    elif mw:
        lines.append(f"Molecular weight: {mw:.1f} Da")

    # Bioavailability
    F = drug.get("bioavailability")
    if F is not None:
        lines.append(f"Oral bioavailability (F): {F * 100:.0f}%")

    # Protein binding / free fraction
    pb = drug.get("protein_binding")
    if pb is not None:
        lines.append(
            f"Protein binding: {pb * 100:.0f}%  →  free fraction: {(1 - pb) * 100:.0f}%"
        )

    # Half-life → elimination rate constant (ke = ln2 / t½)
    hl_str = drug.get("half_life") or ""
    hl_h = _parse_half_life_hours(hl_str)
    if hl_h:
        ke = math.log(2) / hl_h
        lines.append(f"Half-life: {hl_h:.1f} h  →  ke = {ke:.4f} h⁻¹")
        lines.append(f"Time to steady state (≈4×t½): ~{hl_h * 4:.0f} h ({hl_h * 4 / 24:.1f} days)")

    return "\n".join(lines) if lines else "No structured PK data in database."


def _parse_half_life_hours(hl_str: str) -> float | None:
    """Parse textual half-life description (e.g. '12 hours', '1-3 days') to float hours."""
    # Range: take midpoint
    m = re.search(r"([\d.]+)\s*-\s*([\d.]+)\s*(hour|hr|h\b)", hl_str, re.I)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    m = re.search(r"([\d.]+)\s*(hour|hr|h\b)", hl_str, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)\s*-\s*([\d.]+)\s*(day|d\b)", hl_str, re.I)
    if m:
        return ((float(m.group(1)) + float(m.group(2))) / 2) * 24
    m = re.search(r"([\d.]+)\s*(day|d\b)", hl_str, re.I)
    if m:
        return float(m.group(1)) * 24
    m = re.search(r"([\d.]+)\s*(min|minute)", hl_str, re.I)
    if m:
        return float(m.group(1)) / 60
    return None


def _extract_approved_dose(drug: dict) -> str:
    """Try to extract approved dose from drug record (not structured — narrative field)."""
    pharmacodynamics = drug.get("pharmacodynamics") or ""
    half_life = drug.get("half_life") or "unknown"
    return f"Half-life: {half_life}. Pharmacodynamics: {pharmacodynamics[:200]}"
