"""
pubmed_adapter.py — PubMed E-utilities adapter for bulk abstract retrieval.

Uses Biopython Entrez (pip install biopython).

API key recommended for >3 req/s: https://www.ncbi.nlm.nih.gov/account/
"""

from __future__ import annotations

import logging
import time
from typing import Generator

log = logging.getLogger(__name__)

try:
    from Bio import Entrez
    _HAS_BIOPYTHON = True
except ImportError:
    _HAS_BIOPYTHON = False
    log.warning("biopython not installed — PubMed adapter disabled")

DEFAULT_EMAIL = "repurposing-pipeline@example.com"


class PubMedAdapter:
    def __init__(self, email: str = DEFAULT_EMAIL, api_key: str | None = None) -> None:
        if not _HAS_BIOPYTHON:
            raise ImportError("Install biopython: pip install biopython")
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
        self.delay = 0.34 if not api_key else 0.1  # 3/s without key, 10/s with key

    def search(self, query: str, max_results: int = 500) -> list[str]:
        """Return a list of PMIDs matching the query."""
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        time.sleep(self.delay)
        return record["IdList"]

    def fetch_abstracts(self, pmids: list[str], batch_size: int = 200) -> Generator[dict, None, None]:
        """Yield parsed abstract records for a list of PMIDs."""
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            handle = Entrez.efetch(
                db="pubmed",
                id=",".join(batch),
                rettype="xml",
                retmode="xml"
            )
            records = Entrez.read(handle)
            handle.close()
            time.sleep(self.delay)
            for article in records.get("PubmedArticle", []):
                yield self._parse_article(article)

    def _parse_article(self, raw: dict) -> dict:
        medline = raw.get("MedlineCitation", {})
        article = medline.get("Article", {})
        abstract_texts = article.get("Abstract", {}).get("AbstractText", [])
        abstract = " ".join(
            str(t) for t in (abstract_texts if isinstance(abstract_texts, list) else [abstract_texts])
        )
        pmid_elem = medline.get("PMID")
        pmid = str(pmid_elem) if pmid_elem else None
        pub_date = article.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        year = pub_date.get("Year") or pub_date.get("MedlineDate", "")[:4]

        return {
            "pmid": pmid,
            "title": str(article.get("ArticleTitle", "")),
            "abstract": abstract,
            "year": int(year) if str(year).isdigit() else None,
            "authors": [
                f"{a.get('LastName', '')} {a.get('Initials', '')}".strip()
                for a in article.get("AuthorList", [])
                if isinstance(a, dict)
            ],
        }

    def count_cooccurrence(self, term_a: str, term_b: str) -> int:
        """Count PubMed abstracts mentioning both terms."""
        query = f'("{term_a}"[Title/Abstract]) AND ("{term_b}"[Title/Abstract])'
        handle = Entrez.esearch(db="pubmed", term=query, retmax=0)
        record = Entrez.read(handle)
        handle.close()
        time.sleep(self.delay)
        return int(record.get("Count", 0))
