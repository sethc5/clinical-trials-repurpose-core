"""
omim_adapter.py — OMIM genetic disease and gene association adapter.

Requires OMIM API key: https://www.omim.org/api

API docs: https://www.omim.org/help/api
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.omim.org/api"


class OMIMAdapter:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        p = {"apiKey": self.api_key, "format": "json", **(params or {})}
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=p, timeout=30)
        resp.raise_for_status()
        time.sleep(0.25)
        return resp.json()

    def get_entry(self, mim_number: str) -> dict | None:
        """Fetch OMIM entry by MIM number."""
        data = self._get("entry", {"mimNumber": mim_number, "include": "geneMap,text"})
        entries = data.get("omim", {}).get("entryList", [])
        if not entries:
            return None
        return self._parse_entry(entries[0].get("entry", {}))

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search OMIM entries by keyword."""
        data = self._get("entry/search", {"search": query, "limit": limit})
        entries = data.get("omim", {}).get("searchResponse", {}).get("entryList", [])
        return [self._parse_entry(e.get("entry", {})) for e in entries]

    def _parse_entry(self, raw: dict) -> dict:
        gene_map = raw.get("geneMap", {})
        return {
            "omim_id": str(raw.get("mimNumber")),
            "title": raw.get("titles", {}).get("preferredTitle"),
            "mim_type": raw.get("mimType"),
            "gene_symbols": [gene_map.get("geneSymbols", "")],
            "gene_name": gene_map.get("geneName"),
            "chromosomal_location": gene_map.get("chromosomalLocation"),
        }

    def get_genes_for_phenotype(self, mim_number: str) -> list[str]:
        """Return gene symbols associated with a phenotype MIM number."""
        entry = self.get_entry(mim_number)
        if not entry:
            return []
        return [s.strip() for s in entry.get("gene_symbols", [""])[0].split(",") if s.strip()]
