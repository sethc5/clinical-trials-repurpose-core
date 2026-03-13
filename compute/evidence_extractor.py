"""
evidence_extractor.py — T1: LLM-assisted structured evidence extraction from papers.

Extracts evidence type, direction, and strength from PubMed abstracts
using Claude as a structured NLP tool (not creative generation).

Output is stored in the evidence table for T2 synthesis and re-ranking.

Cost note: ~$0.01-0.03 per abstract at Claude Sonnet pricing.
Cache all responses — same abstract may be relevant to multiple pairs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import llm_client

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are extracting structured evidence from a scientific abstract for a drug repurposing analysis.

Drug: {drug_name}
Indication: {indication_name}

Abstract:
---
{abstract}
---

Extract the following as JSON (no prose, only the JSON object):
{{
  "evidence_type": "<one of: clinical, preclinical, epidemiological, mechanistic, genetic, transcriptomic>",
  "source_type": "<one of: paper, trial, case_report, review, database>",
  "strength": "<one of: strong, moderate, weak, conflicting>",
  "direction": "<one of: supporting, opposing, neutral>",
  "summary": "<1-2 sentence summary of the evidence for/against repurposing>",
  "relevant": <true if this abstract contains evidence relevant to drug-indication pair, else false>
}}

Rules:
- Only classify what is explicitly stated in the abstract
- 'strength' = strong only if human clinical data; moderate for animal/mechanistic; weak for in vitro only
- 'direction' = supporting if the data suggests the drug could help the indication
- If no relevant information, set relevant=false and use neutral direction
"""

RESPONSE_CACHE_DIR = Path(".cache/evidence_extractions")


class EvidenceExtractor:
    def __init__(self, model: str = "claude-sonnet-4-20250514", cache: bool = True) -> None:
        self.model = model
        self.use_cache = cache
        if cache:
            RESPONSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        self._ready = True

    def extract(self, abstract: dict, drug_name: str, indication_name: str) -> dict | None:
        """
        Extract structured evidence from a single abstract.

        Returns None if the abstract is not relevant or extraction fails.
        """
        pmid = abstract.get("pmid", "unknown")
        cache_key = self._cache_key(pmid, drug_name, indication_name)

        if self.use_cache:
            cached = self._load_cache(cache_key)
            if cached:
                return cached

        abstract_text = abstract.get("abstract") or ""
        if not abstract_text or len(abstract_text) < 50:
            return None

        prompt = EXTRACTION_PROMPT.format(
            drug_name=drug_name,
            indication_name=indication_name,
            abstract=abstract_text[:3000],  # cap to avoid token explosion
        )

        try:
            result = llm_client.complete_json(prompt, model=self.model)

            if not result.get("relevant", False):
                return None

            output = {
                "source_id": pmid,
                "title": abstract.get("title"),
                "year": abstract.get("year"),
                "evidence_type": result.get("evidence_type", "unknown"),
                "source_type": result.get("source_type", "paper"),
                "strength": result.get("strength", "weak"),
                "direction": result.get("direction", "neutral"),
                "summary": result.get("summary", ""),
            }

            if self.use_cache:
                self._save_cache(cache_key, output)

            return output

        except json.JSONDecodeError as e:
            log.warning(f"Evidence extraction JSON parse failed for PMID={pmid}: {e}")
            return None
        except Exception as e:
            log.error(f"Evidence extraction API error for PMID={pmid}: {e}")
            return None

    @staticmethod
    def _cache_key(pmid: str, drug_name: str, indication_name: str) -> str:
        raw = f"{pmid}|{drug_name}|{indication_name}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _load_cache(self, key: str) -> dict | None:
        path = RESPONSE_CACHE_DIR / f"{key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return None
        return None

    def _save_cache(self, key: str, data: dict) -> None:
        path = RESPONSE_CACHE_DIR / f"{key}.json"
        path.write_text(json.dumps(data))


def extract_evidence(
    drug: dict,
    indication: dict,
    max_papers: int = 20,
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """
    Top-level T1 evidence extraction routine.

    1. Fetches relevant PubMed abstracts for drug+indication
    2. Extracts structured evidence from each relevant abstract
    3. Returns list of evidence items for storage and scoring
    """
    from compute.literature_cooccurrence import search_supporting_abstracts

    drug_name = drug.get("name") or drug.get("drug_id")
    indication_name = indication.get("name") or indication.get("indication_id")

    abstracts = search_supporting_abstracts(drug_name, indication_name, max_results=max_papers)
    if not abstracts:
        return []

    extractor = EvidenceExtractor(model=model)
    evidence_items = []

    for abstract in abstracts:
        item = extractor.extract(abstract, drug_name, indication_name)
        if item:
            evidence_items.append(item)

    log.info(f"Extracted {len(evidence_items)}/{len(abstracts)} relevant evidence items for {drug_name} × {indication_name}")
    return evidence_items
