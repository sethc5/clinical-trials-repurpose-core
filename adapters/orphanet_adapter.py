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
        """
        Return prevalence entries for a disease from `en_product9_prev.xml`.

        Expected `orpha_code` formats: `ORPHA:123`, `ORPHA_123`, or `123`.
        """
        if not self.xml_dir:
            log.warning("Orphanet prevalence lookup requested without xml_dir")
            return None

        xml_path = self.xml_dir / "en_product9_prev.xml"
        if not xml_path.exists():
            log.warning("Orphanet prevalence XML not found: %s", xml_path)
            return None

        wanted_code = self._normalize_orpha_code(orpha_code)
        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        for disorder in root.iter():
            if self._local_name(disorder.tag) != "Disorder":
                continue

            code_raw = self._find_text(disorder, "OrphaCode")
            if self._normalize_orpha_code(code_raw) != wanted_code:
                continue

            name = self._find_text(disorder, "Name")
            prevalence_entries: list[dict] = []
            for prev in self._iter_children(disorder, "Prevalence"):
                prevalence_entries.append(
                    {
                        "type": self._find_text(prev, "PrevalenceType/Name"),
                        "qualification": self._find_text(
                            prev, "PrevalenceQualification/Name"
                        ),
                        "class": self._find_text(prev, "PrevalenceClass/Name"),
                        "validation_status": self._first_text(
                            prev,
                            "ValidationStatus/Name",
                            "ValMoy/Name",
                        ),
                        "source": self._find_text(prev, "Source/Name"),
                    }
                )

            return {
                "orphanet_id": f"ORPHA:{wanted_code}",
                "name": name,
                "prevalence_entries": prevalence_entries,
                "source_file": str(xml_path),
            }
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

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.split("}", 1)[-1]

    def _iter_children(self, elem: ET.Element, local_name: str) -> Generator[ET.Element, None, None]:
        for child in elem.iter():
            if self._local_name(child.tag) == local_name:
                yield child

    def _find_text(self, elem: ET.Element, path: str) -> str | None:
        """Namespace-agnostic element text lookup by slash-separated local names."""
        names = [p for p in path.split("/") if p]
        current_nodes = [elem]
        for name in names:
            next_nodes: list[ET.Element] = []
            for node in current_nodes:
                for child in list(node):
                    if self._local_name(child.tag) == name:
                        next_nodes.append(child)
            if not next_nodes:
                return None
            current_nodes = next_nodes
        text = current_nodes[0].text if current_nodes else None
        return text.strip() if isinstance(text, str) and text.strip() else None

    def _first_text(self, elem: ET.Element, *paths: str) -> str | None:
        for path in paths:
            value = self._find_text(elem, path)
            if value:
                return value
        return None

    @staticmethod
    def _normalize_orpha_code(raw: str | None) -> str:
        value = (raw or "").strip().upper().replace("ORPHA:", "").replace("ORPHA_", "")
        return value
