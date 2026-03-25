#!/usr/bin/env python3
"""
Fetch and store evidence references from Semantic Scholar for decision traceability.

Outputs:
- JSON bundle with raw selected fields
- BibTeX file for citation manager import
- Markdown summary table for quick review

Example:
  python3 scripts/fetch_semantic_scholar_refs.py \
    --query "drug repurposing clinical trial success predictors" \
    --query "evidence hierarchy randomized controlled trial observational study" \
    --tag clinical_build_profiles \
    --limit 8
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "reference" / "sources" / "semantic_scholar"
DEFAULT_ATHANOR_ENV = Path("/home/seth/dev/athanor/.env")
API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_FIELDS = (
    "paperId,title,abstract,year,venue,publicationTypes,citationCount,"
    "influentialCitationCount,externalIds,url,authors.name,openAccessPdf"
)


def _slug(s: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower()).strip("_")
    return raw[:80] if raw else "refs"


def _read_key_from_env_file(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key in {"S2_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"} and value:
            return value
    return None


def resolve_api_key(explicit: str | None, athanor_env: Path) -> str | None:
    if explicit:
        return explicit
    for env_name in ("S2_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"):
        value = os.getenv(env_name)
        if value:
            return value
    return _read_key_from_env_file(athanor_env)


def _choose_doi(external_ids: dict[str, Any] | None) -> str | None:
    if not external_ids:
        return None
    for key in ("DOI", "doi"):
        value = external_ids.get(key)
        if value:
            return str(value)
    return None


def _first_author(authors: list[dict[str, Any]] | None) -> str:
    if not authors:
        return "unknown"
    name = str((authors[0] or {}).get("name") or "unknown")
    return re.sub(r"[^a-zA-Z0-9]+", "", name.split()[-1].lower()) or "unknown"


def _to_bibtex_key(paper: dict[str, Any]) -> str:
    year = str(paper.get("year") or "nd")
    return f"{_first_author(paper.get('authors'))}{year}"


def _to_bibtex_entry(paper: dict[str, Any]) -> str:
    key = _to_bibtex_key(paper)
    title = (paper.get("title") or "").replace("{", "").replace("}", "")
    venue = paper.get("venue") or "Unknown Venue"
    year = paper.get("year") or "n.d."
    url = paper.get("url") or ""
    doi = _choose_doi(paper.get("externalIds"))
    authors = paper.get("authors") or []
    author_field = " and ".join((a.get("name") or "Unknown") for a in authors) or "Unknown"

    lines = [
        f"@article{{{key},",
        f"  title = {{{title}}},",
        f"  author = {{{author_field}}},",
        f"  journal = {{{venue}}},",
        f"  year = {{{year}}},",
    ]
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if url:
        lines.append(f"  url = {{{url}}},")
    lines.append("}")
    return "\n".join(lines)


def search_query(query: str, limit: int, fields: str, api_key: str | None) -> list[dict[str, Any]]:
    params = {
        "query": query,
        "limit": str(limit),
        "fields": fields,
    }
    headers: dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key

    response = requests.get(API_BASE, params=params, headers=headers, timeout=60)
    response.raise_for_status()
    payload = response.json()
    return payload.get("data") or []


def _passes_filters(
    paper: dict[str, Any],
    min_citations: int | None,
    year_from: int | None,
    year_to: int | None,
    require_terms: list[str],
) -> bool:
    citations = int(paper.get("citationCount") or 0)
    if min_citations is not None and citations < min_citations:
        return False

    year = paper.get("year")
    if year_from is not None and isinstance(year, int) and year < year_from:
        return False
    if year_to is not None and isinstance(year, int) and year > year_to:
        return False

    if require_terms:
        haystack = " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                str(paper.get("venue") or ""),
            ]
        ).lower()
        for term in require_terms:
            if term.lower() not in haystack:
                return False
    return True


def _write_markdown_summary(path: Path, rows: list[dict[str, Any]], tag: str, queries: list[str]) -> None:
    lines = [
        f"# Semantic Scholar References — {tag}",
        "",
        f"- Generated UTC: {dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()}",
        f"- Query count: {len(queries)}",
        "",
        "## Queries",
        "",
    ]
    for q in queries:
        lines.append(f"- `{q}`")
    lines.extend(["", "## Papers", "", "| # | Year | Title | Venue | DOI | Citations | URL |", "|---:|---:|---|---|---|---:|---|"])

    for idx, row in enumerate(rows, start=1):
        title = str(row.get("title") or "").replace("|", " ")
        venue = str(row.get("venue") or "").replace("|", " ")
        year = row.get("year") or ""
        doi = _choose_doi(row.get("externalIds")) or ""
        ccount = row.get("citationCount") or 0
        url = row.get("url") or ""
        lines.append(f"| {idx} | {year} | {title} | {venue} | {doi} | {ccount} | {url} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch references from Semantic Scholar")
    parser.add_argument("--query", action="append", required=True, help="Search query (repeatable)")
    parser.add_argument("--limit", type=int, default=10, help="Results per query")
    parser.add_argument("--tag", required=True, help="Logical tag for output file names")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--fields", type=str, default=DEFAULT_FIELDS)
    parser.add_argument("--api-key", type=str, default=None, help="Override API key")
    parser.add_argument("--athanor-env", type=Path, default=DEFAULT_ATHANOR_ENV)
    parser.add_argument("--min-citations", type=int, default=None)
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--year-to", type=int, default=None)
    parser.add_argument(
        "--require-term",
        action="append",
        default=[],
        help="Require term in title/abstract/venue (repeatable)",
    )
    args = parser.parse_args()

    api_key = resolve_api_key(args.api_key, args.athanor_env)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag_slug = _slug(args.tag)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    query_results: list[dict[str, Any]] = []
    by_paper_id: dict[str, dict[str, Any]] = {}
    for query in args.query:
        try:
            papers = search_query(query=query, limit=args.limit, fields=args.fields, api_key=api_key)
        except requests.HTTPError as exc:
            raise SystemExit(f"Semantic Scholar query failed for {query!r}: {exc}") from exc
        query_results.append({"query": query, "n_results": len(papers)})
        for paper in papers:
            if not _passes_filters(
                paper=paper,
                min_citations=args.min_citations,
                year_from=args.year_from,
                year_to=args.year_to,
                require_terms=args.require_term,
            ):
                continue
            pid = str(paper.get("paperId") or "")
            if not pid:
                continue
            if pid not in by_paper_id:
                by_paper_id[pid] = paper

    rows = sorted(
        by_paper_id.values(),
        key=lambda r: (-(r.get("citationCount") or 0), -(r.get("influentialCitationCount") or 0), -(r.get("year") or 0)),
    )

    base = f"{stamp}_{tag_slug}"
    json_path = out_dir / f"{base}.json"
    bib_path = out_dir / f"{base}.bib"
    md_path = out_dir / f"{base}.md"

    payload = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "tag": args.tag,
        "queries": query_results,
        "result_count_unique": len(rows),
        "fields": args.fields.split(","),
        "filters": {
            "min_citations": args.min_citations,
            "year_from": args.year_from,
            "year_to": args.year_to,
            "require_term": args.require_term,
        },
        "papers": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    bib_entries = [_to_bibtex_entry(p) for p in rows]
    bib_path.write_text("\n\n".join(bib_entries) + ("\n" if bib_entries else ""), encoding="utf-8")

    _write_markdown_summary(md_path, rows=rows, tag=args.tag, queries=args.query)

    key_state = "present" if api_key else "absent (unauthenticated requests)"
    print(f"Saved Semantic Scholar refs: {len(rows)} unique papers")
    print(f"  key: {key_state}")
    print(f"  json: {json_path}")
    print(f"  bib:  {bib_path}")
    print(f"  md:   {md_path}")


if __name__ == "__main__":
    main()
