"""
findings_generator.py — Drive correlation_scanner and write FINDINGS.md.

Pulls all T2 survivors from the database, runs cross-candidate pattern
detection, and formats the results as a readable FINDINGS.md in the
project root.

Usage:
    python findings_generator.py --db results/repurposing.db
    python findings_generator.py --db results/repurposing.db --out FINDINGS.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_t2_candidates(db_path: str) -> list[dict]:
    """Return all T2-passing runs with drug/indication names."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT r.*,
                   d.name  AS drug_name,
                   d.mechanism_of_action,
                   i.name  AS indication_name
            FROM runs r
            LEFT JOIN drugs      d ON r.drug_id = d.drug_id
            LEFT JOIN indications i ON r.indication_id = i.indication_id
            WHERE r.t2_pass = 1
            ORDER BY r.composite_score DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_findings(db_path: str) -> list[dict]:
    """Return findings previously written by correlation_scanner."""
    with _connect(db_path) as conn:
        try:
            rows = conn.execute("SELECT * FROM findings ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []


def _score_bar(score: float, width: int = 20) -> str:
    filled = int(round(score * width))
    return "[" + "█" * filled + "░" * (width - filled) + f"] {score:.2f}"


def build_findings_markdown(
    candidates: list[dict],
    findings: list[dict],
    project_name: str = "Repurposing Pipeline",
) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    n = len(candidates)

    sections: list[str] = []

    # Header
    sections.append(f"# FINDINGS — {project_name}")
    sections.append(f"*Generated: {now} | {n} T2 candidates*")
    sections.append("")

    if not candidates:
        sections.append("No T2 candidates found. Run the full pipeline first.")
        return "\n".join(sections)

    # Top candidates table
    sections.append("## Top Repurposing Candidates")
    sections.append("")
    sections.append(
        "| Rank | Drug | Indication | Composite Score | Evidence | Mechanistic | Safety |"
    )
    sections.append(
        "|------|------|------------|-----------------|----------|-------------|--------|"
    )
    for i, c in enumerate(candidates[:20], 1):
        drug = c.get("drug_name") or c.get("drug_id")
        ind = c.get("indication_name") or c.get("indication_id")
        cs = c.get("composite_score") or 0.0
        ev = c.get("t1_evidence_score") or 0.0
        mech = c.get("t1_mechanistic_score") or 0.0
        safe = c.get("t1_safety_score") or 0.0
        sections.append(
            f"| {i} | {drug} | {ind} | {cs:.3f} | {ev:.2f} | {mech:.2f} | {safe:.2f} |"
        )
    sections.append("")

    # Detailed candidate cards
    sections.append("## Candidate Profiles")
    sections.append("")
    for c in candidates[:10]:
        drug = c.get("drug_name") or c.get("drug_id")
        ind = c.get("indication_name") or c.get("indication_id")
        cs = c.get("composite_score") or 0.0

        sections.append(f"### {drug} → {ind}")
        sections.append("")
        sections.append(f"**Composite Score:** {_score_bar(min(cs, 1.0))}")
        sections.append("")
        moa = c.get("mechanism_of_action") or "Unknown"
        sections.append(f"**Mechanism of Action:** {moa[:300]}")
        sections.append("")

        # T2 synthesis narrative
        synthesis = c.get("t2_synthesis")
        if synthesis:
            sections.append("**Evidence Synthesis:**")
            sections.append("")
            sections.append(synthesis[:800])
            sections.append("")

        # Dose
        dose_raw = c.get("t2_dose_rationale") or {}
        if isinstance(dose_raw, str):
            try:
                dose_raw = json.loads(dose_raw)
            except Exception:
                dose_raw = {}
        if dose_raw:
            proposed = dose_raw.get("proposed_dose") or dose_raw.get("dose_range_for_trial")
            if proposed:
                sections.append(f"**Proposed Dose:** {proposed}")
                sections.append("")

        dossier = Path(f"results/dossiers/{c.get('drug_id')}_{c.get('indication_id')}_dossier.md")
        if dossier.exists():
            sections.append(f"**Full dossier:** [{dossier}]({dossier})")
            sections.append("")

        sections.append("---")
        sections.append("")

    # Cross-candidate findings
    if findings:
        sections.append("## Cross-Candidate Patterns")
        sections.append("")
        sections.append(
            f"{len(findings)} cross-candidate findings detected by correlation scanner."
        )
        sections.append("")
        for f in findings[:10]:
            ftype = f.get("finding_type") or "finding"
            data = f.get("finding_data") or {}
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            sections.append(f"**{ftype.replace('_', ' ').title()}**")
            if data:
                for k, v in list(data.items())[:4]:
                    sections.append(f"  - {k}: {v}")
            sections.append("")

    # Stats
    sections.append("## Pipeline Statistics")
    sections.append("")
    sections.append(f"- **T2 candidates:** {n}")
    unique_drugs = len({c.get("drug_id") for c in candidates})
    unique_indications = len({c.get("indication_id") for c in candidates})
    sections.append(f"- **Unique drugs represented:** {unique_drugs}")
    sections.append(f"- **Unique indications covered:** {unique_indications}")
    if candidates:
        avg_score = sum(c.get("composite_score") or 0.0 for c in candidates) / len(candidates)
        sections.append(f"- **Mean composite score:** {avg_score:.3f}")
    sections.append("")
    sections.append("---")
    sections.append("*Findings generated by clinical-trial-repurposing-pipeline-core*")

    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate FINDINGS.md from pipeline results")
    parser.add_argument("--db", required=True, help="Path to repurposing SQLite database")
    parser.add_argument("--out", default="FINDINGS.md", help="Output Markdown path (default: FINDINGS.md)")
    parser.add_argument("--project-name", default="Repurposing Pipeline", dest="project_name")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        raise SystemExit(1)

    candidates = load_t2_candidates(args.db)
    findings = load_findings(args.db)

    content = build_findings_markdown(candidates, findings, project_name=args.project_name)
    out_path = Path(args.out)
    out_path.write_text(content)
    print(f"FINDINGS.md written to {out_path} ({len(candidates)} T2 candidates)")


if __name__ == "__main__":
    main()
