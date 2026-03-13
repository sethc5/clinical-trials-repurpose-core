"""
drugbank_adapter.py — DrugBank XML/API adapter.

Provides drug mechanism, primary/secondary targets, and safety profile.

Free tier API: https://go.drugbank.com/releases/latest
Full licensed XML: https://www.drugbank.ca/releases/latest (requires license)

NOTE: Full target/mechanism data requires licensed access.
      Free tier covers basic drug info and limited target data.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator

import requests

log = logging.getLogger(__name__)

DRUGBANK_API = "https://api.drugbank.com/v1"
NS = "http://www.drugbank.ca"  # XML namespace


class DrugBankAdapter:
    """
    Adapter for DrugBank. Supports two modes:
      1. API mode (api_key required, limited free tier data)
      2. XML mode (full licensed XML dump — preferred for full target coverage)
    """

    def __init__(self, api_key: str | None = None, xml_path: str | Path | None = None) -> None:
        self.api_key = api_key
        self.xml_path = Path(xml_path) if xml_path else None
        self.session = requests.Session()
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"

    # ------------------------------------------------------------------
    # API mode
    # ------------------------------------------------------------------

    def get_drug_by_id(self, drugbank_id: str) -> dict | None:
        """Fetch drug data via API by DrugBank ID (e.g. 'DB00945')."""
        if not self.api_key:
            raise RuntimeError("DrugBank API key required for API mode")
        resp = self.session.get(f"{DRUGBANK_API}/drugs/{drugbank_id}", timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._parse_api_response(resp.json())

    def search_drugs(self, query: str, limit: int = 50) -> list[dict]:
        """Search drugs by name via API."""
        if not self.api_key:
            raise RuntimeError("DrugBank API key required for API mode")
        resp = self.session.get(
            f"{DRUGBANK_API}/drugs",
            params={"q": query, "per_page": limit},
            timeout=30
        )
        resp.raise_for_status()
        return [self._parse_api_response(d) for d in resp.json().get("drugs", [])]

    def _parse_api_response(self, raw: dict) -> dict:
        return {
            "drug_id": raw.get("drugbank_id"),
            "name": raw.get("name"),
            "generic_name": raw.get("synonyms", [None])[0] if raw.get("synonyms") else None,
            "drug_type": raw.get("drug_type"),
            "status": raw.get("groups", ["unknown"])[0],
            "mechanism_of_action": raw.get("mechanism_of_action"),
            "pharmacodynamics": raw.get("pharmacodynamics"),
            "half_life": raw.get("half_life"),
            "molecular_formula": raw.get("molecular_formula"),
            "mw": raw.get("molecular_weight"),
            "logp": raw.get("logp"),
            "smiles": raw.get("smiles"),
            "inchi_key": raw.get("inchi_key"),
            "primary_targets": self._extract_targets(raw.get("targets", [])),
            "pathway_ids": self._extract_pathway_ids(raw.get("pathways", [])),
            "source": "drugbank",
        }

    # ------------------------------------------------------------------
    # XML mode (licensed full dump)
    # ------------------------------------------------------------------

    def iter_drugs_from_xml(self) -> Generator[dict, None, None]:
        """Parse the full DrugBank XML and yield drug records."""
        if not self.xml_path or not self.xml_path.exists():
            raise FileNotFoundError(f"DrugBank XML not found at {self.xml_path}")

        log.info(f"Parsing DrugBank XML: {self.xml_path}")
        for _event, elem in ET.iterparse(str(self.xml_path), events=("end",)):
            tag = elem.tag.replace(f"{{{NS}}}", "")
            if tag == "drug" and elem.get("type") in ("small molecule", "biotech"):
                yield self._parse_xml_drug(elem)
                elem.clear()  # free memory

    def _parse_xml_drug(self, elem: ET.Element) -> dict:
        def txt(tag: str) -> str | None:
            el = elem.find(f"{{{NS}}}{tag}")
            return el.text if el is not None else None

        drug_id_elem = elem.find(f"{{{NS}}}drugbank-id[@primary='true']")
        drug_id = drug_id_elem.text if drug_id_elem is not None else None

        # Targets
        targets = []
        for t in elem.findall(f".//{{{NS}}}target"):
            gene = t.findtext(f".//{{{NS}}}gene-name")
            uniprot = t.findtext(f".//{{{NS}}}id")
            action = t.findtext(f".//{{{NS}}}action")
            if gene or uniprot:
                targets.append({"gene_name": gene, "uniprot_id": uniprot, "action": action})

        # Pathways
        pathway_ids = [
            p.findtext(f"{{{NS}}}smpdb-id") or p.findtext(f"{{{NS}}}kegg-map-id", "")
            for p in elem.findall(f".//{{{NS}}}pathway")
        ]

        return {
            "drug_id": drug_id,
            "name": txt("name"),
            "drug_type": elem.get("type"),
            "mechanism_of_action": txt("mechanism-of-action"),
            "pharmacodynamics": txt("pharmacodynamics"),
            "half_life": txt("half-life"),
            "molecular_formula": txt("molecular-formula"),
            "smiles": txt("smiles"),
            "inchi_key": txt("inchi-key"),
            "primary_targets": targets[:3],   # first 3 = primary
            "all_targets": targets,
            "pathway_ids": [p for p in pathway_ids if p],
            "source": "drugbank_xml",
        }

    @staticmethod
    def _extract_targets(raw_targets: list[dict]) -> list[dict]:
        return [
            {
                "uniprot_id": t.get("uniprot_id"),
                "gene_name": t.get("gene_name"),
                "affinity": t.get("known_action"),
            }
            for t in (raw_targets or [])[:3]
        ]

    @staticmethod
    def _extract_pathway_ids(raw_pathways: list[dict]) -> list[str]:
        return [p.get("smpdb_id") or p.get("kegg_id", "") for p in (raw_pathways or [])]
