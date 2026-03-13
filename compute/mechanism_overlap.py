"""
mechanism_overlap.py — T0: Jaccard overlap of drug pathway/MeSH term sets.

Computes how much the drug's known mechanism overlaps with the target
disease's pathway signature. Fast database-lookup operation (no API calls).
"""

from __future__ import annotations

import json
import math
from typing import Any


def compute_mechanism_overlap(
    drug: dict,
    indication: dict,
    filter_config: Any,
) -> float:
    """
    Compute Jaccard overlap between drug pathways and indication pathways.

    J(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        drug: drug record from RepurposingDB
        indication: indication record from RepurposingDB
        filter_config: T0FilterConfig

    Returns:
        Jaccard similarity [0, 1]. 0 if either has no pathways.
    """
    drug_pathways = _parse_pathway_set(drug.get("pathway_ids"))
    indication_pathways = _parse_pathway_set(indication.get("pathway_ids"))

    if not drug_pathways or not indication_pathways:
        return 0.0

    intersection = len(drug_pathways & indication_pathways)
    union = len(drug_pathways | indication_pathways)

    return intersection / union if union > 0 else 0.0


def compute_go_term_overlap(drug: dict, indication: dict) -> float:
    """
    Jaccard overlap on GO biological process terms.

    Drug GO terms derived from its primary targets' annotations.
    Indication GO terms from disease gene ontology annotations.
    """
    drug_go = _parse_go_set(drug.get("all_targets"))
    indication_go = _parse_go_set(indication.get("go_terms"))

    if not drug_go or not indication_go:
        return 0.0

    intersection = len(drug_go & indication_go)
    union = len(drug_go | indication_go)
    return intersection / union if union > 0 else 0.0


def compute_gene_set_overlap(drug: dict, indication: dict) -> dict:
    """
    Compute gene-set overlap (Fisher's exact test) between drug targets
    and indication disease genes.

    Returns {'overlap_count': int, 'jaccard': float, 'p_value': float}
    """
    drug_genes = _parse_gene_set(drug.get("primary_targets") or drug.get("all_targets"))
    indication_genes = _parse_gene_set(indication.get("disease_genes"))

    if not drug_genes or not indication_genes:
        return {"overlap_count": 0, "jaccard": 0.0, "p_value": 1.0}

    overlap = drug_genes & indication_genes
    union = drug_genes | indication_genes
    jaccard = len(overlap) / len(union) if union else 0.0

    # Fisher's exact using scipy if available
    p_value = _fisher_p_value(
        len(overlap),
        len(drug_genes - overlap),
        len(indication_genes - overlap),
        background_size=20000,  # approximate human genome coding genes
    )

    return {
        "overlap_count": len(overlap),
        "overlap_genes": list(overlap),
        "jaccard": round(jaccard, 4),
        "p_value": round(p_value, 6),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pathway_set(pathway_ids: Any) -> set[str]:
    if isinstance(pathway_ids, list):
        return {p.strip() for p in pathway_ids if p}
    if isinstance(pathway_ids, str):
        try:
            return {p.strip() for p in json.loads(pathway_ids) if p}
        except Exception:
            return {pathway_ids.strip()} if pathway_ids.strip() else set()
    return set()


def _parse_go_set(field: Any) -> set[str]:
    if isinstance(field, list):
        return {str(t) for t in field if t}
    if isinstance(field, str):
        try:
            return {str(t) for t in json.loads(field) if t}
        except Exception:
            return set()
    return set()


def _parse_gene_set(targets: Any) -> set[str]:
    """Extract gene symbols from a targets list or gene list."""
    if not targets:
        return set()
    if isinstance(targets, str):
        try:
            targets = json.loads(targets)
        except Exception:
            return set()
    genes = set()
    for t in targets:
        if isinstance(t, dict):
            gene = t.get("gene_name") or t.get("gene_symbol") or t.get("uniprot_id")
            if gene:
                genes.add(gene)
        elif isinstance(t, str):
            genes.add(t)
    return genes


def _fisher_p_value(
    a: int,  # hits in both
    b: int,  # drug only
    c: int,  # indication only
    background_size: int = 20000,
) -> float:
    """One-tailed Fisher's exact test p-value (enrichment direction)."""
    try:
        from scipy.stats import fisher_exact
        d = background_size - a - b - c
        _, p = fisher_exact([[a, b], [c, max(d, 0)]], alternative="greater")
        return float(p)
    except ImportError:
        # Fallback: no scipy — return approximate via hypergeometric
        return _hypergeometric_p(a, a + b, a + c, background_size)


def _hypergeometric_p(k: int, n: int, K: int, N: int) -> float:
    """Approximate hypergeometric p-value (upper tail)."""
    if n == 0 or K == 0 or N == 0:
        return 1.0
    # Very rough approximation when scipy unavailable
    expected = n * K / N
    if k <= expected:
        return 1.0
    # Rough Z-score
    var = n * K * (N - K) * (N - n) / (N * N * (N - 1)) if N > 1 else 1
    if var <= 0:
        return 0.001
    z = (k - expected) / math.sqrt(var)
    # Approximate normal p-value
    return max(1e-10, 0.5 * math.erfc(z / math.sqrt(2)))
