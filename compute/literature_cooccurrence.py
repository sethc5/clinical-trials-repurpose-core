"""
literature_cooccurrence.py — T0.25: PubMed abstract co-occurrence statistics.

Counts how frequently a drug name and disease name co-appear in PubMed abstracts.
Noisy signal used as one of three orthogonal T0.25 filters.

Note: Co-occurrence alone is insufficient (context-insensitive). Use alongside
network proximity and transcriptomic scores for higher confidence.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def count_pubmed_cooccurrence(
    drug_name: str,
    indication_name: str,
    lit_config,  # LiteratureConfig
) -> int:
    """
    Count PubMed abstract co-occurrences of drug name and indication name.

    Args:
        drug_name: drug preferred name
        indication_name: disease/indication name
        lit_config: LiteratureConfig with min_cooccurrence threshold

    Returns:
        Integer count of co-occurring abstracts.
    """
    from adapters.pubmed_adapter import PubMedAdapter

    try:
        pubmed = PubMedAdapter()
        count = pubmed.count_cooccurrence(drug_name, indication_name)
        log.debug(f"PubMed co-occurrence '{drug_name}' × '{indication_name}': {count}")
        return count
    except Exception as e:
        log.warning(f"PubMed co-occurrence failed for {drug_name} × {indication_name}: {e}")
        return 0


def search_supporting_abstracts(
    drug_name: str,
    indication_name: str,
    max_results: int = 20,
) -> list[dict]:
    """
    Return the top PubMed abstracts co-mentioning drug and indication.

    Used at T1 for seeding the evidence extraction step.
    """
    from adapters.pubmed_adapter import PubMedAdapter

    query = f'"{drug_name}"[Title/Abstract] AND "{indication_name}"[Title/Abstract]'
    try:
        pubmed = PubMedAdapter()
        pmids = pubmed.search(query, max_results=max_results)
        if not pmids:
            return []
        abstracts = list(pubmed.fetch_abstracts(pmids))
        return abstracts
    except Exception as e:
        log.warning(f"PubMed abstract search failed: {e}")
        return []


def search_mechanism_evidence(
    drug_name: str,
    mechanism_terms: list[str],
    indication_name: str,
    max_results: int = 20,
) -> list[dict]:
    """
    Search for papers mentioning drug, mechanism terms, AND indication.

    More specific than name co-occurrence — requires mechanism overlap
    to be mentioned in the same abstract.
    """
    from adapters.pubmed_adapter import PubMedAdapter

    mech_query = " OR ".join(f'"{t}"' for t in mechanism_terms[:5])  # cap to 5 terms
    query = (
        f'("{drug_name}"[Title/Abstract]) '
        f'AND ("{indication_name}"[Title/Abstract]) '
        f'AND ({mech_query}[Title/Abstract])'
    )
    try:
        pubmed = PubMedAdapter()
        pmids = pubmed.search(query, max_results=max_results)
        return list(pubmed.fetch_abstracts(pmids)) if pmids else []
    except Exception as e:
        log.warning(f"Mechanism evidence search failed: {e}")
        return []
