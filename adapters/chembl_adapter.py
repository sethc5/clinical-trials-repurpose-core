"""
chembl_adapter.py — ChEMBL bioactivity and target data adapter.

Uses chembl_webresource_client (pip install chembl_webresource_client).
Falls back to REST API if client not available.

API: https://www.ebi.ac.uk/chembl/api/data/
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    from chembl_webresource_client.new_client import new_client
    _HAS_CLIENT = True
except ImportError:
    _HAS_CLIENT = False
    log.warning("chembl_webresource_client not installed — using REST API fallback")

import requests

CHEMBL_REST = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLAdapter:
    def __init__(self) -> None:
        if _HAS_CLIENT:
            self.molecule = new_client.molecule
            self.target = new_client.target
            self.activity = new_client.activity
            self.mechanism = new_client.mechanism
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Drug / molecule lookup
    # ------------------------------------------------------------------

    def get_drug_by_name(self, name: str) -> dict | None:
        """Return ChEMBL compound record by preferred name."""
        if _HAS_CLIENT:
            results = self.molecule.filter(pref_name__iexact=name)
            return self._parse_molecule(results[0]) if results else None
        # REST fallback
        resp = self.session.get(
            f"{CHEMBL_REST}/molecule.json",
            params={"pref_name__iexact": name, "limit": 1},
            timeout=30
        )
        resp.raise_for_status()
        molecules = resp.json().get("molecules", [])
        return self._parse_molecule(molecules[0]) if molecules else None

    def get_drug_by_chembl_id(self, chembl_id: str) -> dict | None:
        if _HAS_CLIENT:
            results = self.molecule.filter(molecule_chembl_id=chembl_id)
            return self._parse_molecule(results[0]) if results else None
        resp = self.session.get(f"{CHEMBL_REST}/molecule/{chembl_id}.json", timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._parse_molecule(resp.json())

    def _parse_molecule(self, raw: dict) -> dict:
        props = raw.get("molecule_properties") or {}
        struct = raw.get("molecule_structures") or {}
        return {
            "drug_id": raw.get("molecule_chembl_id"),
            "name": raw.get("pref_name"),
            "drug_type": raw.get("molecule_type", "").lower().replace(" ", "_"),
            "status": raw.get("max_phase"),   # 4 = approved
            "mw": props.get("full_mwt"),
            "logp": props.get("alogp"),
            "molecular_formula": props.get("full_molformula"),
            "smiles": struct.get("canonical_smiles"),
            "inchi_key": struct.get("standard_inchi_key"),
            "source": "chembl",
        }

    # ------------------------------------------------------------------
    # Target / mechanism data
    # ------------------------------------------------------------------

    def get_mechanisms(self, chembl_id: str) -> list[dict]:
        """Return mechanism of action records for a compound."""
        if _HAS_CLIENT:
            records = self.mechanism.filter(molecule_chembl_id=chembl_id)
        else:
            resp = self.session.get(
                f"{CHEMBL_REST}/mechanism.json",
                params={"molecule_chembl_id": chembl_id, "limit": 50},
                timeout=30
            )
            resp.raise_for_status()
            records = resp.json().get("mechanisms", [])
        return [
            {
                "target_chembl_id": r.get("target_chembl_id"),
                "mechanism_of_action": r.get("mechanism_of_action"),
                "action_type": r.get("action_type"),
            }
            for r in records
        ]

    def get_bioactivities(
        self,
        chembl_id: str,
        standard_type: str = "IC50",
        limit: int = 100,
    ) -> list[dict]:
        """Return bioactivity records for a compound."""
        params: dict[str, Any] = {
            "molecule_chembl_id": chembl_id,
            "standard_type": standard_type,
            "limit": limit,
        }
        if _HAS_CLIENT:
            records = list(self.activity.filter(**params))
        else:
            resp = self.session.get(f"{CHEMBL_REST}/activity.json", params=params, timeout=30)
            resp.raise_for_status()
            records = resp.json().get("activities", [])
        return [
            {
                "target_chembl_id": r.get("target_chembl_id"),
                "target_pref_name": r.get("target_pref_name"),
                "standard_type": r.get("standard_type"),
                "standard_value": r.get("standard_value"),
                "standard_units": r.get("standard_units"),
                "pchembl_value": r.get("pchembl_value"),
            }
            for r in records
        ]
