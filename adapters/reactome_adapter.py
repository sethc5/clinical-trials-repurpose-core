"""
reactome_adapter.py — Reactome pathway analysis adapter.

Provides pathway enrichment analysis and pathway membership data
using the Reactome API and gseapy.

API: https://reactome.org/ContentService/
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://reactome.org/ContentService"


class ReactomeAdapter:
    def __init__(self) -> None:
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        resp = self.session.get(f"{BASE_URL}{endpoint}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_pathways_for_gene(self, gene_symbol: str, species: str = "Homo sapiens") -> list[dict]:
        """Return Reactome pathways containing a given gene symbol."""
        try:
            data = self._get(f"/data/pathways/low/diagram/entity/{gene_symbol}/allForms")
            return [
                {
                    "pathway_id": p.get("stId"),
                    "name": p.get("displayName"),
                    "species": p.get("speciesName"),
                }
                for p in (data if isinstance(data, list) else [])
                if p.get("speciesName", "").startswith("Homo sapiens")
            ]
        except Exception as e:
            log.warning(f"Reactome query failed for {gene_symbol}: {e}")
            return []

    def get_pathway_participants(self, pathway_id: str) -> list[str]:
        """Return gene symbols in a Reactome pathway."""
        try:
            data = self._get(f"/data/pathway/{pathway_id}/containedEvents")
            genes = set()
            for event in (data if isinstance(data, list) else []):
                inputs = event.get("input", [])
                for inp in inputs:
                    name = inp.get("name")
                    if name:
                        genes.add(name)
            return list(genes)
        except Exception as e:
            log.warning(f"Reactome participant query failed for {pathway_id}: {e}")
            return []

    def run_enrichment(
        self,
        gene_list: list[str],
        p_cutoff: float = 0.05,
        top_n: int = 20,
    ) -> list[dict]:
        """
        Submit a gene list to Reactome pathway enrichment analysis.

        Returns top enriched pathways sorted by p-value.
        """
        try:
            import gseapy as gp
            results = gp.enrichr(
                gene_list=gene_list,
                gene_sets=["Reactome_2022"],
                organism="Human",
                outdir=None,
                cutoff=p_cutoff,
            )
            df = results.results.sort_values("Adjusted P-value").head(top_n)
            return df.to_dict("records")
        except ImportError:
            log.error("gseapy not installed: pip install gseapy")
            return []
        except Exception as e:
            log.warning(f"Reactome enrichment failed: {e}")
            return []
