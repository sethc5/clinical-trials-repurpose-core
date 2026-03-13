"""
kegg_adapter.py — KEGG pathway data adapter.

Retrieves pathway membership lists and gene sets for overlap analysis.
Uses the bioservices KEGG client or KEGG REST API directly.

API: https://www.kegg.jp/kegg/rest/keggapi.html
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://rest.kegg.jp"


class KEGGAdapter:
    def __init__(self) -> None:
        self.session = requests.Session()
        self._pathway_gene_cache: dict[str, list[str]] = {}

    def _get_text(self, endpoint: str) -> str:
        resp = self.session.get(f"{BASE_URL}/{endpoint}", timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)
        return resp.text

    def get_pathway_genes(self, pathway_id: str) -> list[str]:
        """
        Return human gene symbols in a KEGG pathway.

        Args:
            pathway_id: e.g. 'hsa04150' (mTOR signaling, human)

        Returns:
            List of gene symbols (HGNC)
        """
        if pathway_id in self._pathway_gene_cache:
            return self._pathway_gene_cache[pathway_id]

        text = self._get_text(f"link/hsa/{pathway_id}")
        gene_ids = []
        for line in text.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                gene_ids.append(parts[1].replace("hsa:", ""))

        # Convert NCBI gene IDs to symbols via KEGG
        symbols = self._convert_gene_ids(gene_ids) if gene_ids else []
        self._pathway_gene_cache[pathway_id] = symbols
        return symbols

    def _convert_gene_ids(self, ncbi_ids: list[str]) -> list[str]:
        """Convert NCBI gene IDs to gene symbols via KEGG."""
        symbols = []
        for ncbi_id in ncbi_ids[:100]:  # cap to avoid huge requests
            try:
                text = self._get_text(f"get/hsa:{ncbi_id}")
                for line in text.split("\n"):
                    if line.startswith("SYMBOL"):
                        symbol = line.split()[1].rstrip(",")
                        symbols.append(symbol)
                        break
            except Exception:
                pass
        return symbols

    def get_pathways_for_gene(self, gene_symbol: str) -> list[str]:
        """Return KEGG pathway IDs containing a gene."""
        try:
            text = self._get_text(f"link/pathway/{gene_symbol}")
            pathway_ids = []
            for line in text.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    pathway_ids.append(parts[1].replace("path:", ""))
            return pathway_ids
        except Exception:
            return []

    def get_pathway_info(self, pathway_id: str) -> dict:
        """Return name and description for a pathway ID."""
        text = self._get_text(f"get/{pathway_id}")
        info: dict = {"pathway_id": pathway_id}
        for line in text.split("\n"):
            if line.startswith("NAME"):
                info["name"] = " ".join(line.split()[1:])
            elif line.startswith("DESCRIPTION"):
                info["description"] = " ".join(line.split()[1:])
        return info
