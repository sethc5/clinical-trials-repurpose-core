"""
evidence_synthesizer.py — T2: Systematic evidence synthesis via LLM.

Aggregates all evidence gathered at T1 into a coherent narrative
that a clinician or biotech team could evaluate. Uses Claude Opus
for highest-quality synthesis at this final tier.

Output: narrative Markdown evidence summary for the dossier.
"""

from __future__ import annotations

import json
import logging

import llm_client

log = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are synthesizing scientific evidence for a drug repurposing assessment.

Drug: {drug_name} ({mechanism})
Target Indication: {indication_name}

Evidence items ({n_items} total):
---
{evidence_json}
---

Pathway overlap: {pathway_summary}
Adverse event profile: {ae_summary}

Write a concise systematic evidence synthesis (300-400 words) covering:
1. **Mechanistic rationale**: Why could this drug work for this indication?
2. **Supporting evidence**: What is the strongest available evidence?
3. **Gaps and limitations**: What is unknown or conflicting?
4. **Overall assessment**: One sentence conclusion with confidence level (low/moderate/high).

Write in clear, scientific prose suitable for a drug development team.
Do not speculate beyond what the evidence supports.
"""


def synthesize_evidence(
    drug: dict,
    indication: dict,
    db,  # RepurposingDB
    model: str = "claude-opus-4-20250514",
) -> str:
    """
    Generate a narrative evidence synthesis for a T2 candidate.

    Returns Markdown text or empty string if synthesis fails.
    """
    # Gather T1 evidence
    run_id = _get_run_id(drug["drug_id"], indication["indication_id"], db)
    evidence_items = db.get_evidence_for_run(run_id) if run_id else []

    evidence_json = json.dumps(
        [{"type": e.get("evidence_type"), "direction": e.get("direction"),
          "strength": e.get("strength"), "summary": e.get("summary")}
         for e in evidence_items[:20]],
        indent=2
    )

    drug_name = drug.get("name") or drug.get("drug_id")
    indication_name = indication.get("name") or indication.get("indication_id")
    mechanism = drug.get("mechanism_of_action") or "unknown mechanism"

    prompt = SYNTHESIS_PROMPT.format(
        drug_name=drug_name,
        mechanism=mechanism[:300],
        indication_name=indication_name,
        n_items=len(evidence_items),
        evidence_json=evidence_json,
        pathway_summary="See pathway overlap data.",
        ae_summary="See adverse event profile.",
    )

    try:
        return llm_client.complete(prompt, model=model)
    except Exception as e:
        log.error(f"Evidence synthesis failed: {e}")
        return f"Synthesis unavailable: {e}"


def _get_run_id(drug_id: str, indication_id: str, db) -> int | None:
    """Look up the run_id for a drug-indication pair."""
    try:
        with db._conn() as conn:
            row = conn.execute(
                "SELECT run_id FROM runs WHERE drug_id=? AND indication_id=?",
                (drug_id, indication_id)
            ).fetchone()
        return row["run_id"] if row else None
    except Exception:
        return None
