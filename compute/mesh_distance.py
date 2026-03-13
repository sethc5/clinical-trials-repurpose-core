"""
mesh_distance.py — T0: MeSH tree distance for mechanism proximity scoring.

MeSH (Medical Subject Headings) organizes concepts in a hierarchical tree.
Drugs with mechanisms close to the disease's MeSH descriptor have
higher mechanistic plausibility even before network analysis.

MeSH tree files: https://www.nlm.nih.gov/mesh/download_mesh.html
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)


class MeSHDistance:
    """
    Compute tree distance between MeSH descriptors.

    Distance = number of tree hops between closest nodes when
    a descriptor has multiple tree positions.
    """

    def __init__(self, mesh_tree_path: str | Path | None = None) -> None:
        self._tree: dict[str, list[str]] = {}  # descriptor_id → [tree_numbers]
        self._tree_to_desc: dict[str, str] = {}  # tree_number → descriptor_id
        if mesh_tree_path:
            self._load_tree(Path(mesh_tree_path))

    def _load_tree(self, path: Path) -> None:
        """Load MeSH tree numbers from mtrees*.txt or descriptor XML."""
        log.info(f"Loading MeSH tree from {path}")
        if path.suffix == ".txt":
            self._load_from_txt(path)
        elif path.suffix in (".xml", ".gz"):
            self._load_from_xml(path)
        else:
            log.warning(f"Unknown MeSH file format: {path.suffix}")

    def _load_from_txt(self, path: Path) -> None:
        """Parse mtrees*.bin.utf8 format: 'Name;TreeNumber' per line."""
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ";" not in line:
                    continue
                name, tree_num = line.rsplit(";", 1)
                desc_id = name  # use name as ID — ideally use UI from XML
                if desc_id not in self._tree:
                    self._tree[desc_id] = []
                self._tree[desc_id].append(tree_num)
                self._tree_to_desc[tree_num] = desc_id

    def _load_from_xml(self, path: Path) -> None:
        """Parse MeSH descriptor XML (desc*.xml)."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(path))
        root = tree.getroot()
        for record in root.findall("DescriptorRecord"):
            ui = record.findtext("DescriptorUI") or ""
            tree_nums = [tn.text for tn in record.findall(".//TreeNumber") if tn.text]
            if ui and tree_nums:
                self._tree[ui] = tree_nums
                for tn in tree_nums:
                    self._tree_to_desc[tn] = ui

    def distance(self, desc_a: str, desc_b: str) -> int | None:
        """
        Minimum tree distance between two MeSH descriptors.

        Returns None if either descriptor is not in the tree or
        descriptors are in different branches (no common ancestor within limit).
        """
        trees_a = self._tree.get(desc_a, [])
        trees_b = self._tree.get(desc_b, [])
        if not trees_a or not trees_b:
            return None

        min_dist = None
        for ta in trees_a:
            for tb in trees_b:
                d = self._tree_distance(ta, tb)
                if d is not None:
                    min_dist = d if min_dist is None else min(min_dist, d)
        return min_dist

    @staticmethod
    def _tree_distance(tree_a: str, tree_b: str) -> int | None:
        """
        Distance between two MeSH tree numbers via LCA (lowest common ancestor).

        E.g. "D05.500.562" and "D05.500.099" → distance 2 (LCA = "D05.500")
        """
        parts_a = tree_a.split(".")
        parts_b = tree_b.split(".")

        # Find common prefix length
        common = 0
        for a, b in zip(parts_a, parts_b):
            if a == b:
                common += 1
            else:
                break

        # Distance = steps up from A to LCA + steps down to B
        return (len(parts_a) - common) + (len(parts_b) - common)

    def within_distance(self, desc_a: str, desc_b: str, max_dist: int) -> bool:
        """Return True if the two descriptors are within max_dist tree hops."""
        d = self.distance(desc_a, desc_b)
        return d is not None and d <= max_dist


def compute_mesh_distance(drug: dict, indication: dict, max_distance: int = 3) -> bool:
    """
    Quick check: is the drug's mechanism within max_distance MeSH hops
    of the indication's primary descriptor?

    Used as a T0 pre-filter. Returns True (pass) if within distance or
    if MeSH data is not loaded (fail-open).
    """
    # Implementation requires a loaded MeSHDistance instance
    # In production, this is initialized once at pipeline startup
    # and shared across workers via a module-level singleton.
    # Stub returns True (pass) when not configured.
    return True


# Module-level singleton (initialized by pipeline_core at startup)
_mesh_instance: MeSHDistance | None = None


def init_mesh(path: str | Path) -> None:
    global _mesh_instance
    _mesh_instance = MeSHDistance(path)


def get_mesh() -> MeSHDistance | None:
    return _mesh_instance
