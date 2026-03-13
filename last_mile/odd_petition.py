"""
odd_petition.py — FDA Orphan Drug Designation (ODD) petition generator.

Produces a Markdown draft petition per 21 CFR Part 316 for a drug-indication
pair flagged as orphan (indication.orphan_status=True OR prevalence < 200,000 US).

Sections:
  I.   Cover Letter (human-fill stub)
  II.  Drug Description (INN, structure, mechanism from DB)
  III. Disease Description + Prevalence Justification (Orphanet + DB)
  IV.  Medical Plausibility (LLM-generated from evidence_summary)
  V.   Prior Clinical Experience (from trials table + evidence items)
  VI.  Bibliography (sorted by year)

Usage:
    python -m last_mile.odd_petition --config config.yaml --drug DRUGBANKID --indication RAREDISEASE
    python -m last_mile.odd_petition --config config.yaml  # auto-selects top orphan candidate

Output:
    results/ODD_PETITION_<drug>_<indication>_<date>.md

Dependencies:
    jinja2, llm_client, db_utils, config_schema
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import typer
    from rich.console import Console
    _cli_available = True
except ImportError:
    _cli_available = False

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    _jinja_available = True
except ImportError:
    _jinja_available = False

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_schema import PipelineConfig
from db_utils import RepurposingDB
import llm_client

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# ODD eligibility: US prevalence threshold (people)
_ODD_PREVALENCE_US = 200_000

# ---------------------------------------------------------------------------
# Plausibility narrative prompt
# ---------------------------------------------------------------------------

_PLAUSIBILITY_PROMPT = """You are writing Section IV (Medical Plausibility) of an FDA Orphan Drug Designation petition.

Drug: {drug_name}
Mechanism: {mechanism}
Target Indication: {indication_name} (ICD-10: {icd10})
Evidence Summary from Pipeline: {evidence_summary}
Supporting Evidence Items: {evidence_items}

Write a 400-600 word medical plausibility narrative. Address:
1. How the drug's mechanism addresses the known disease pathophysiology
2. Available preclinical evidence (in vitro, animal models)
3. Clinical clues (case reports, retrospective studies, related indications)
4. Scientific rationale and gaps to be addressed in a clinical trial

Write in third-person scientific prose. This will be submitted to FDA OOPD.
Do NOT speculate beyond what the evidence supports.
"""

_EXPERIENCE_PROMPT = """Summarize prior clinical experience for this drug in or near this rare indication.

Drug: {drug_name}
Indication: {indication_name}
Trials: {trials_json}
Evidence items: {evidence_items}

Write 200-300 words covering:
- Any completed clinical trials (phase, results, outcomes)
- Compassionate use / case reports if trials are absent
- Adverse events observed in prior use
- Overall safety signal relevant to this patient population

Scientific tone, third person. Will be submitted to FDA.
"""


# ---------------------------------------------------------------------------
# Core build function
# ---------------------------------------------------------------------------

def generate(
    db: RepurposingDB,
    drug_id: str,
    indication_id: str,
    output_dir: Path | str = Path("results"),
    skip_llm: bool = False,
) -> Path:
    """
    Generate a draft ODD petition for a drug-indication pair.

    Returns the Path of the written Markdown file.
    """
    if not _jinja_available:
        raise ImportError("jinja2 is required: pip install jinja2")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    drug = db.get_drug(drug_id)
    if drug is None:
        raise ValueError(f"Drug {drug_id!r} not found in DB")
    indication = db.get_indication(indication_id)
    if indication is None:
        raise ValueError(f"Indication {indication_id!r} not found in DB")

    # Pull run data
    run = _get_run(db, drug_id, indication_id)
    evidence_items = db.get_evidence_for_run(run["run_id"]) if run else []
    trials = db.get_trials_for_pair(drug_id, indication_id)

    # Prevalence check
    prevalence = indication.get("prevalence") or 0
    orphan_status = indication.get("orphan_status") or (prevalence > 0 and prevalence < _ODD_PREVALENCE_US)

    # LLM narrative sections
    if skip_llm:
        plausibility_text = "[FILL IN: Medical plausibility narrative (21 CFR 316.20(b)(4))]"
        experience_text = "[FILL IN: Prior clinical experience summary]"
    else:
        plausibility_text = _generate_plausibility(drug, indication, run, evidence_items)
        experience_text = _generate_experience(drug, indication, trials, evidence_items)

    # Bibliography from evidence items
    bibliography = _build_bibliography(evidence_items)

    # Render template
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("odd_petition.md.j2")

    rendered = tmpl.render(
        drug=drug,
        indication=indication,
        run=run or {},
        prevalence=prevalence,
        orphan_us_threshold=_ODD_PREVALENCE_US,
        orphan_status=orphan_status,
        plausibility_text=plausibility_text,
        experience_text=experience_text,
        bibliography=bibliography,
        trials=trials[:10],
        generated_at=datetime.now(timezone.utc).isoformat(),
        today=date.today().isoformat(),
    )

    slug = f"{drug_id}_{indication_id}_{date.today().strftime('%Y%m%d')}"
    out_path = output_dir / f"ODD_PETITION_{slug}.md"
    out_path.write_text(rendered)
    log.info("ODD petition written to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _generate_plausibility(
    drug: dict,
    indication: dict,
    run: dict | None,
    evidence_items: list[dict],
) -> str:
    evidence_summary = (run or {}).get("t2_evidence_summary") or "Not yet generated."
    top_evidence = json.dumps(
        [{"type": e.get("evidence_type"), "direction": e.get("direction"),
          "strength": e.get("strength"), "summary": e.get("summary")}
         for e in evidence_items[:10]],
        indent=2,
    )
    prompt = _PLAUSIBILITY_PROMPT.format(
        drug_name=drug.get("name") or drug_id,
        mechanism=(drug.get("mechanism_of_action") or "unknown")[:400],
        indication_name=indication.get("name") or indication["indication_id"],
        icd10=indication.get("icd10_code") or "N/A",
        evidence_summary=(evidence_summary or "")[:600],
        evidence_items=top_evidence,
    )
    try:
        return llm_client.complete(prompt)
    except Exception as exc:
        log.warning("Plausibility LLM call failed: %s", exc)
        return f"[FILL IN: Medical plausibility narrative (21 CFR 316.20(b)(4))]\n\n<!-- Error: {exc} -->"


def _generate_experience(
    drug: dict,
    indication: dict,
    trials: list[dict],
    evidence_items: list[dict],
) -> str:
    evidence_subset = [e for e in evidence_items if e.get("source_type") in ("trial", "paper", "case_report")]
    prompt = _EXPERIENCE_PROMPT.format(
        drug_name=drug.get("name") or drug["drug_id"],
        indication_name=indication.get("name") or indication["indication_id"],
        trials_json=json.dumps(
            [{"trial_id": t.get("trial_id"), "phase": t.get("phase"),
              "status": t.get("status"), "result": t.get("result_summary")}
             for t in trials[:8]],
            indent=2,
        ),
        evidence_items=json.dumps(
            [{"type": e.get("source_type"), "summary": e.get("summary"), "year": e.get("year")}
             for e in evidence_subset[:8]],
            indent=2,
        ),
    )
    try:
        return llm_client.complete(prompt)
    except Exception as exc:
        log.warning("Experience LLM call failed: %s", exc)
        return f"[FILL IN: Prior clinical experience summary]\n\n<!-- Error: {exc} -->"


def _build_bibliography(evidence_items: list[dict]) -> list[dict]:
    bib = []
    for e in evidence_items:
        if e.get("source_id") and e.get("title"):
            bib.append({
                "pmid": e.get("source_id"),
                "title": e.get("title"),
                "year": e.get("year") or "n.d.",
            })
    return sorted(bib, key=lambda x: str(x.get("year", "")), reverse=True)


def _get_run(db: RepurposingDB, drug_id: str, indication_id: str) -> dict | None:
    runs = db.get_runs_at_tier(0)
    for r in runs:
        if r.get("drug_id") == drug_id and r.get("indication_id") == indication_id:
            return r
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if _cli_available:
    console = Console()
    app = typer.Typer(help="Generate an ODD petition draft for a repurposing candidate.")

    @app.command()
    def cli(
        config: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
        drug: Optional[str] = typer.Option(None, "--drug", help="Drug ID (DB primary key)"),
        indication: Optional[str] = typer.Option(None, "--indication", help="Indication ID"),
        output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
        skip_llm: bool = typer.Option(False, "--skip-llm"),
    ) -> None:
        cfg = PipelineConfig.from_yaml(config)
        db = RepurposingDB(cfg.output.db_path)

        drug_id = drug
        indication_id = indication

        # Auto-select top orphan candidate if not specified
        if not drug_id or not indication_id:
            candidates = db.get_runs_at_tier(2)
            orphan_candidates = [r for r in candidates if r.get("fto_checked") or True]
            if not orphan_candidates:
                console.print("[red]No T2-passing candidates found. Run the pipeline first.[/red]")
                raise typer.Exit(1)
            top = orphan_candidates[0]
            drug_id = drug_id or top["drug_id"]
            indication_id = indication_id or top["indication_id"]

        out_dir = output_dir or Path(cfg.output.results_dir)
        out_path = generate(db, drug_id, indication_id, out_dir, skip_llm=skip_llm)
        console.print(f"[green]ODD petition written → {out_path}[/green]")

    if __name__ == "__main__":
        app()
