"""
pathway_analyzer.py — T1: KEGG/Reactome pathway enrichment and overlap depth.

Goes beyond T0 Jaccard overlap to perform full enrichment analysis:
- Which specific pathways are shared?
- How central are the shared genes in those pathways?
- What is the enrichment significance?
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def analyze_pathway_overlap(drug: dict, indication: dict) -> dict:
    """
    Full pathway overlap analysis between drug targets and disease gene set.

    Returns:
        {
            "shared_pathways": [{pathway_id, name, drug_genes_in_pathway,
                                  disease_genes_in_pathway, overlap_genes}],
            "drug_enriched_pathways": [...],
            "disease_enriched_pathways": [...],
            "overlap_n": int,
            "top_pathway": str | None,
        }
    """
    from adapters.kegg_adapter import KEGGAdapter
    from adapters.reactome_adapter import ReactomeAdapter

    drug_genes = _extract_genes(drug.get("all_targets") or drug.get("primary_targets"))
    disease_genes = _extract_genes(indication.get("disease_genes"))
    drug_pathway_ids = _parse_list(drug.get("pathway_ids"))
    indication_pathway_ids = _parse_list(indication.get("pathway_ids"))

    if not drug_genes and not drug_pathway_ids:
        return {"shared_pathways": [], "overlap_n": 0, "top_pathway": None}

    kegg = KEGGAdapter()
    reactome = ReactomeAdapter()

    # Get gene sets for all pathways
    shared_pathways = []
    examined = set(drug_pathway_ids) | set(indication_pathway_ids)

    for pathway_id in examined:
        try:
            if pathway_id.startswith("hsa") or pathway_id.startswith("R-HSA"):
                if pathway_id.startswith("hsa"):
                    pathway_genes = set(kegg.get_pathway_genes(pathway_id))
                else:
                    pathway_genes = set(reactome.get_pathway_participants(pathway_id))

                d_in_pathway = set(drug_genes) & pathway_genes
                dis_in_pathway = set(disease_genes) & pathway_genes
                overlap = d_in_pathway & dis_in_pathway

                if overlap:
                    shared_pathways.append({
                        "pathway_id": pathway_id,
                        "drug_genes_in_pathway": list(d_in_pathway),
                        "disease_genes_in_pathway": list(dis_in_pathway),
                        "overlap_genes": list(overlap),
                        "overlap_count": len(overlap),
                    })
        except Exception as e:
            log.debug(f"Pathway analysis failed for {pathway_id}: {e}")

    shared_pathways.sort(key=lambda x: -x["overlap_count"])

    # Enrichment analysis (gseapy) for additional pathways
    if drug_genes:
        try:
            enriched = reactome.run_enrichment(list(drug_genes), top_n=10)
        except Exception:
            enriched = []
    else:
        enriched = []

    return {
        "shared_pathways": shared_pathways[:20],
        "drug_enriched_pathways": enriched,
        "overlap_n": len(shared_pathways),
        "top_pathway": shared_pathways[0]["pathway_id"] if shared_pathways else None,
    }


def _extract_genes(field: Any) -> list[str]:
    if not field:
        return []
    if isinstance(field, str):
        try:
            field = json.loads(field)
        except Exception:
            return []
    if isinstance(field, list):
        genes = []
        for item in field:
            if isinstance(item, dict):
                g = item.get("gene_name") or item.get("gene_symbol")
                if g:
                    genes.append(g)
            elif isinstance(item, str):
                genes.append(item)
        return genes
    return []


def _parse_list(field: Any) -> list[str]:
    if isinstance(field, list):
        return field
    if isinstance(field, str):
        try:
            return json.loads(field)
        except Exception:
            return [field] if field else []
    return []
