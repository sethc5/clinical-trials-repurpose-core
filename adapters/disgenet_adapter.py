"""
disgenet_adapter.py — DisGeNET disease-gene association adapter.

DisGeNET provides curated disease-gene associations with evidence scores.
API docs: https://www.disgenet.org/api/

Requires DisGeNET API key: https://www.disgenet.org/plans
"""

from __future__ import annotations

import logging
import time
from typing import Generator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://www.disgenet.org/api"


class DisGeNETAdapter:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    def _get(self, endpoint: str, params: dict | None = None) -> list | dict:
        resp = self.session.get(f"{BASE_URL}{endpoint}", params=params, timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.json()

    def get_genes_for_disease(self, disease_id: str, min_score: float = 0.1) -> list[dict]:
        """
        Return gene associations for a disease (MeSH, OMIM, or UMLS CUI).

        Args:
            disease_id: MeSH ID (e.g. 'C0002395'), OMIM ID, or UMLS CUI
            min_score: minimum DisGeNET association score (0-1)

        Returns:
            [{gene_name, uniprot_id, score, n_pmids, evidence_index}, ...]
        """
        data = self._get(f"/gda/disease/{disease_id}", {"min_score": min_score, "limit": 500})
        if not isinstance(data, list):
            return []
        return [
            {
                "gene_name": r.get("gene_id"),
                "gene_symbol": r.get("gene_symbol"),
                "uniprot_id": None,  # requires separate lookup
                "score": r.get("score"),
                "dsi": r.get("dsi"),  # disease specificity index
                "dpi": r.get("dpi"),  # disease pleiotropy index
                "n_pmids": r.get("pmid_count"),
                "source_db": r.get("source"),
            }
            for r in data
        ]

    def get_diseases_for_gene(self, gene_symbol: str, min_score: float = 0.1) -> list[dict]:
        """Return diseases associated with a gene symbol."""
        data = self._get(f"/gda/gene/{gene_symbol}", {"min_score": min_score, "limit": 500})
        if not isinstance(data, list):
            return []
        return [
            {
                "disease_id": r.get("disease_umls_cui"),
                "disease_name": r.get("disease_name"),
                "mesh_id": r.get("disease_meshid"),
                "score": r.get("score"),
            }
            for r in data
        ]

    def get_shared_genes(self, disease_id_a: str, disease_id_b: str) -> list[str]:
        """Return gene symbols shared between two diseases — useful for mechanism overlap."""
        genes_a = {r["gene_symbol"] for r in self.get_genes_for_disease(disease_id_a)}
        genes_b = {r["gene_symbol"] for r in self.get_genes_for_disease(disease_id_b)}
        return list(genes_a & genes_b)
