"""
trial_protocol.py — CONSORT / ICH E6(R2) Phase II trial protocol scaffold.

Takes T2 trial_designer output from the DB and wraps it in a full CONSORT-
compliant protocol document. Produces Markdown (convertible to DOCX with
pandoc or python-docx).

Each section maps to ICH E6(R2) / 21 CFR 312.23(a)(6) requirements:
  1. Title page & Contacts
  2. Synopsis
  3. Objectives & Endpoints (from trial_design)
  4. Study Design (from trial_design: design_type, control_arm, blinding)
  5. Patient Population (from trial_design: inclusion/exclusion, biomarker enrichment)
  6. Study Treatments (from dose_rationale)
  7. Statistical Analysis Plan (from trial_design: sample_size, alpha, power)
  8. Safety Monitoring
  9. Regulatory Considerations (from trial_design)
 10. CONSORT Checklist (rendered from consort_checklist.md.j2)

Usage:
    python -m last_mile.trial_protocol --config config.yaml --drug DRUGBANKID --indication RAREDISEASE
    python -m last_mile.trial_protocol  # auto-selects top T2 candidate

Output:
    results/TRIAL_PROTOCOL_<drug>_<indication>_<date>.md

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

# ---------------------------------------------------------------------------
# Synopsis prompt
# ---------------------------------------------------------------------------

_SYNOPSIS_PROMPT = """Write a structured clinical trial synopsis for submission to an ethics committee.

Drug: {drug_name} (approved for: {approved_indications})
Mechanism: {mechanism}
Target Indication: {indication_name}
Trial Design: {design_type}
Primary Endpoint: {primary_endpoint}
Sample Size: {sample_size} participants
Duration: {duration_months} months
Proposed Dose: {proposed_dose}
Patient Population: {population}

Write the synopsis in 250-350 words. Include:
1. Rationale and background (1-2 sentences)
2. Study objectives (primary and 2-3 secondary)
3. Study design overview
4. Patient population (inclusion summary, biomarker enrichment if any)
5. Study duration and follow-up
6. Expected risks and benefits

Third-person, clinical scientific prose. ICH E6(R2) compliant style.
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
    Generate a CONSORT Phase II protocol scaffold for a drug-indication pair.

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

    run = _get_run(db, drug_id, indication_id)
    if run is None:
        raise ValueError(f"No pipeline run found for {drug_id} → {indication_id}")

    # Parse JSON fields from run
    trial_design = _parse_json_field(run.get("t2_trial_design"))
    dose_rationale = _parse_json_field(run.get("t2_dose_rationale"))
    biomarkers = _parse_json_field(run.get("t2_biomarkers"))
    competitive = _parse_json_field(run.get("t2_competitive_landscape"))

    design_type = trial_design.get("design_type", "randomized_controlled") if trial_design else "randomized_controlled"
    primary_ep = trial_design.get("primary_endpoint", {}) if trial_design else {}
    proposed_dose = dose_rationale.get("proposed_dose", "[FILL IN]") if dose_rationale else "[FILL IN]"
    sample_size = (trial_design.get("sample_size") or {}).get("n", "[FILL IN]") if trial_design else "[FILL IN]"
    duration_months = trial_design.get("duration_months", "[FILL IN]") if trial_design else "[FILL IN]"

    if skip_llm:
        synopsis = "[FILL IN: Trial synopsis per ICH E6(R2) §6.4]"
    else:
        synopsis = _generate_synopsis(drug, indication, trial_design, dose_rationale)

    # Render main protocol template
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("phase2_protocol.md.j2")

    rendered = tmpl.render(
        drug=drug,
        indication=indication,
        run=run,
        trial_design=trial_design or {},
        dose_rationale=dose_rationale or {},
        biomarkers=biomarkers or [],
        competitive=competitive or {},
        synopsis=synopsis,
        proposed_dose=proposed_dose,
        sample_size=sample_size,
        duration_months=duration_months,
        design_type=design_type,
        primary_endpoint=primary_ep,
        generated_at=datetime.now(timezone.utc).isoformat(),
        today=date.today().isoformat(),
        protocol_version="0.1-DRAFT",
    )

    slug = f"{drug_id}_{indication_id}_{date.today().strftime('%Y%m%d')}"
    out_path = output_dir / f"TRIAL_PROTOCOL_{slug}.md"
    out_path.write_text(rendered)
    log.info("Trial protocol written to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _generate_synopsis(
    drug: dict,
    indication: dict,
    trial_design: dict | None,
    dose_rationale: dict | None,
) -> str:
    td = trial_design or {}
    dr = dose_rationale or {}
    primary_ep = td.get("primary_endpoint") or {}
    approved = json.dumps(drug.get("approved_indications") or [], ensure_ascii=False)[:200]

    prompt = _SYNOPSIS_PROMPT.format(
        drug_name=drug.get("name") or drug["drug_id"],
        approved_indications=approved,
        mechanism=(drug.get("mechanism_of_action") or "unknown")[:300],
        indication_name=indication.get("name") or indication["indication_id"],
        design_type=td.get("design_type", "randomized_controlled"),
        primary_endpoint=json.dumps(primary_ep),
        sample_size=(td.get("sample_size") or {}).get("n", "TBD"),
        duration_months=td.get("duration_months", "TBD"),
        proposed_dose=dr.get("proposed_dose", "TBD"),
        population=td.get("biomarker_enrichment", {}).get("enrichment_strategy", "Adult patients with diagnosis"),
    )
    try:
        return llm_client.complete(prompt)
    except Exception as exc:
        log.warning("Synopsis LLM call failed: %s", exc)
        return f"[FILL IN: Trial synopsis]\n\n<!-- Error: {exc} -->"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(value) -> dict | list | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


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
    app = typer.Typer(help="Generate a CONSORT Phase II trial protocol scaffold.")

    @app.command()
    def cli(
        config: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
        drug: Optional[str] = typer.Option(None, "--drug"),
        indication: Optional[str] = typer.Option(None, "--indication"),
        output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
        skip_llm: bool = typer.Option(False, "--skip-llm"),
    ) -> None:
        cfg = PipelineConfig.from_yaml(config)
        db = RepurposingDB(cfg.output.db_path)

        drug_id = drug
        indication_id = indication

        if not drug_id or not indication_id:
            candidates = db.get_runs_at_tier(2)
            if not candidates:
                console.print("[red]No T2-passing candidates found. Run the pipeline first.[/red]")
                raise typer.Exit(1)
            top = candidates[0]
            drug_id = drug_id or top["drug_id"]
            indication_id = indication_id or top["indication_id"]

        out_dir = output_dir or Path(cfg.output.results_dir)
        out_path = generate(db, drug_id, indication_id, out_dir, skip_llm=skip_llm)
        console.print(f"[green]Trial protocol written → {out_path}[/green]")

    if __name__ == "__main__":
        app()
