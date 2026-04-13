"""
lincs_adapter.py — LINCS L1000 transcriptomic signature adapter.

LINCS L1000 contains gene expression signatures for ~20,000 compounds
across multiple cell lines. Used for transcriptomic drug-disease matching.

Data access: https://clue.io/ (API key required for full access)
Alternative: processed signature files from GEO (GSE92742, GSE70138)
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CLUE_API = "https://api.clue.io/api"


class LINCSAdapter:
    """
    Adapter for LINCS L1000 / CMap portal.

    Two data access modes:
      1. clue.io REST API (api_key required)
      2. Local GEO file cache (processed .gctx files via cmapPy)
    """

    def __init__(self, api_key: str | None = None, local_data_dir: str | Path | None = None) -> None:
        self.api_key = api_key
        self.local_data_dir = Path(local_data_dir) if local_data_dir else None
        self.session = requests.Session()
        if api_key:
            self.session.headers["user_key"] = api_key

    def get_drug_signature(self, drug_name: str, cell_line: str = "A549") -> dict | None:
        """
        Return the transcriptomic signature (top up/down genes) for a drug.

        Returns:
            {
                "pert_iname": drug_name,
                "cell_id": cell_line,
                "up_genes": [...],   # gene symbols upregulated
                "down_genes": [...], # gene symbols downregulated
                "n_genes": int
            }
        """
        if self.api_key:
            return self._get_signature_api(drug_name, cell_line)
        if self.local_data_dir:
            return self._get_signature_local(drug_name, cell_line)
        log.warning("No LINCS data source configured")
        return None

    def _get_signature_api(self, drug_name: str, cell_line: str) -> dict | None:
        try:
            resp = self.session.get(
                f"{CLUE_API}/sigs",
                params={
                    "where": f'{{"pert_iname":"{drug_name}","cell_id":"{cell_line}"}}',
                    "fields": '["up_genes","dn_genes","pert_iname","cell_id"]',
                    "limit": 1,
                },
                timeout=30
            )
            resp.raise_for_status()
            results = resp.json()
            if not results:
                return None
            r = results[0]
            return {
                "pert_iname": r.get("pert_iname"),
                "cell_id": r.get("cell_id"),
                "up_genes": r.get("up_genes", []),
                "down_genes": r.get("dn_genes", []),
                "n_genes": len(r.get("up_genes", [])) + len(r.get("dn_genes", [])),
            }
        except Exception as e:
            log.error(f"LINCS API error for {drug_name}: {e}")
            return None

    def _get_signature_local(self, drug_name: str, cell_line: str) -> dict | None:
        """Load signature from local .gctx files via cmapPy when configured."""
        try:
            import cmapPy.pandasGEXpress.parse_gctx as _pg  # noqa: F401
        except ImportError:
            log.error("cmapPy not installed: pip install cmapPy")
            return None
        log.warning(
            "Local LINCS mode requested for %s/%s but no local parser mapping is configured; "
            "set API key mode or implement local file routing.",
            drug_name,
            cell_line,
        )
        return None

    def compute_reversal_score(
        self,
        drug_signature: dict,
        disease_signature: dict,
    ) -> float:
        """
        Compute transcriptomic reversal score between drug and disease signatures.

        Score > 0: drug reverses disease (therapeutic signal)
        Score < 0: drug mimics disease (contraindicated)
        """
        drug_up = set(drug_signature.get("up_genes", []))
        drug_dn = set(drug_signature.get("down_genes", []))
        dis_up = set(disease_signature.get("up_genes", []))
        dis_dn = set(disease_signature.get("down_genes", []))

        if not (drug_up | drug_dn) or not (dis_up | dis_dn):
            return 0.0

        # Reversal: drug down ∩ disease up (good) + drug up ∩ disease down (good)
        reversal_hits = len(drug_dn & dis_up) + len(drug_up & dis_dn)
        # Concordance: drug up ∩ disease up (bad) + drug down ∩ disease down (bad)
        concordance_hits = len(drug_up & dis_up) + len(drug_dn & dis_dn)

        total = reversal_hits + concordance_hits
        if total == 0:
            return 0.0
        return (reversal_hits - concordance_hits) / total
