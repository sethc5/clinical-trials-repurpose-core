"""
string_adapter.py — STRING protein-protein interaction network adapter.

STRING provides functional protein interaction networks with confidence scores.
Used for drug target → disease gene network proximity (T0.25).

API docs: https://string-db.org/help/api/
Recommended confidence threshold: >700 (high confidence)
"""

from __future__ import annotations

import logging
from functools import lru_cache

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://string-db.org/api/json"
SPECIES_HUMAN = 9606
DEFAULT_CONFIDENCE = 700  # 0-1000


class STRINGAdapter:
    def __init__(
        self,
        species: int = SPECIES_HUMAN,
        min_confidence: int = DEFAULT_CONFIDENCE,
    ) -> None:
        self.species = species
        self.min_confidence = min_confidence
        self.session = requests.Session()

    def _post(self, endpoint: str, data: dict) -> list[dict]:
        resp = self.session.post(f"{BASE_URL}/{endpoint}", data=data, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def get_interactions(self, proteins: list[str], limit: int = 500) -> list[dict]:
        """
        Return interaction records for a list of proteins.

        Args:
            proteins: list of gene symbols or UniProt IDs
            limit: maximum number of interactions per protein

        Returns:
            [{stringId_A, stringId_B, preferredName_A, preferredName_B, score}, ...]
        """
        data = {
            "identifiers": "%0d".join(proteins),
            "species": self.species,
            "required_score": self.min_confidence,
            "limit": limit,
            "caller_identity": "repurposing-pipeline",
        }
        return self._post("network", data)

    def get_network_as_edgelist(self, proteins: list[str]) -> list[tuple[str, str, float]]:
        """Return (gene_a, gene_b, score) tuples for networkx graph construction."""
        interactions = self.get_interactions(proteins)
        return [
            (
                r["preferredName_A"],
                r["preferredName_B"],
                r["score"] / 1000.0,
            )
            for r in interactions
        ]

    def get_neighbors(self, protein: str, degree: int = 1) -> list[str]:
        """Return protein neighbors up to given degree in STRING network."""
        interactions = self.get_interactions([protein])
        neighbors = set()
        for r in interactions:
            if r["preferredName_A"] == protein:
                neighbors.add(r["preferredName_B"])
            else:
                neighbors.add(r["preferredName_A"])
        return list(neighbors)

    def shortest_path_length(self, source_genes: list[str], target_genes: list[str]) -> float | None:
        """
        Compute the minimum shortest path between any source gene and any target gene.

        Uses networkx after fetching the relevant subnetwork.
        Returns None if no path exists within the network.
        """
        import networkx as nx

        all_genes = list(set(source_genes) | set(target_genes))
        if not all_genes:
            return None

        # Fetch subgraph for all relevant genes
        edges = self.get_network_as_edgelist(all_genes)
        G = nx.Graph()
        G.add_weighted_edges_from(edges)

        min_path = float("inf")
        for src in source_genes:
            for tgt in target_genes:
                try:
                    path_len = nx.shortest_path_length(G, src, tgt)
                    min_path = min(min_path, path_len)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass

        return min_path if min_path < float("inf") else None
