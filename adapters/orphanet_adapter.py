"""
orphanet_adapter.py — Orphanet rare disease database adapter.

Orphanet provides rare disease ontology, gene associations, and prevalence data.
Free XML exports: https://www.orphadata.com/orpha-nomenclature/

API (partial): https://api.orphacode.org/
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator

log = logging.getLogger(__name__)

ORPHANET_API = "https://api.orphacode.org/EN/ClinicalEntity"


class OrphanetAdapter:
    """
    Adapter for Orphanet rare disease database.

    Supports XML file mode (full data export) or API mode (partial).
    Recommended: download full XML from orphadata.com for complete gene data.
    """

    def __init__(self, xml_dir: str | Path | None = None) -> None:
        self.xml_dir = Path(xml_dir) if xml_dir else None

    def iter_diseases_from_xml(self, xml_path: str | Path) -> Generator[dict, None, None]:
        """
        Parse Orphanet XML gene-disease associations export.

        File: 'en_product6.xml' (disease-gene associations)
        Download: https://www.orphadata.com/alignment/ → ORPHA/GENE
        """
        xml_path = Path(xml_path)
        if not xml_path.exists():
            raise FileNotFoundError(f"Orphanet XML not found: {xml_path}")

        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        for disorder in root.iter("Disorder"):
            orpha_num = disorder.findtext("OrphaCode")
            name = disorder.findtext("Name")
            if not orpha_num or not name:
                continue

            genes = []
            for assoc in disorder.iter("DisorderGeneAssociation"):
                gene_elem = assoc.find("Gene")
                if gene_elem is not None:
                    gene_symbol = gene_elem.findtext("Symbol")
                    gene_name = gene_elem.findtext("Name")
                    assoc_type = assoc.findtext("DisorderGeneAssociationType/Name")
                    if gene_symbol:
                        genes.append({
                            "gene_symbol": gene_symbol,
                            "gene_name": gene_name,
                            "association_type": assoc_type,
                        })

            yield {
                "orphanet_id": f"ORPHA:{orpha_num}",
                "name": name,
                "disease_genes": genes,
                "orphan_status": True,
            }

    def get_prevalence(self, orpha_code: str) -> dict | None:
        """Return prevalence data for a rare disease (from prevalence XML)."""
        # Prevalence data in en_product9_prev.xml — stub
        return None

    def search_by_gene(self, gene_symbol: str, xml_path: str | Path | None = None) -> list[dict]:
        """Return all Orphanet diseases associated with a gene symbol."""
        if not xml_path and self.xml_dir:
            xml_path = self.xml_dir / "en_product6.xml"
        if not xml_path:
            raise ValueError("xml_path or xml_dir required")
        return [
            d for d in self.iter_diseases_from_xml(xml_path)
            if any(g["gene_symbol"] == gene_symbol for g in d.get("disease_genes", []))
        ]
