"""
config_schema.py — Pydantic v2 config validation for the repurposing pipeline.

Validates config.yaml files before pipeline execution.

Usage:
    python config_schema.py --validate path/to/config.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Nested filter models
# ---------------------------------------------------------------------------

class T0FilterConfig(BaseModel):
    require_mechanism_pathway_overlap: bool = True
    min_pathway_overlap_jaccard: float = Field(default=0.05, ge=0.0, le=1.0)
    exclude_black_box_for_population: bool = True
    exclude_active_trials_same_indication: bool = True
    exclude_definitive_trial_failures: bool = True
    max_mechanism_distance: int = Field(default=3, ge=1)


class NetworkProximityConfig(BaseModel):
    max_shortest_path: int = Field(default=2, ge=1)
    min_z_score: float = -1.5


class TranscriptomicConfig(BaseModel):
    min_reversal_score: float = Field(default=0.3, ge=0.0, le=1.0)
    min_genes_matched: int = Field(default=10, ge=1)


class LiteratureConfig(BaseModel):
    min_cooccurrence: int = Field(default=3, ge=0)


class T025FilterConfig(BaseModel):
    network_proximity: NetworkProximityConfig = NetworkProximityConfig()
    transcriptomic: TranscriptomicConfig = TranscriptomicConfig()
    literature: LiteratureConfig = LiteratureConfig()
    failed_trial_handling: str = "flag_not_exclude"

    @field_validator("failed_trial_handling")
    @classmethod
    def validate_failed_trial_handling(cls, v: str) -> str:
        allowed = {"flag_not_exclude", "exclude", "downweight"}
        if v not in allowed:
            raise ValueError(f"failed_trial_handling must be one of {allowed}")
        return v


class T1FilterConfig(BaseModel):
    min_evidence_score: float = Field(default=0.4, ge=0.0, le=1.0)
    min_mechanistic_score: float = Field(default=0.35, ge=0.0, le=1.0)
    min_safety_score: float = Field(default=0.5, ge=0.0, le=1.0)
    max_papers_to_extract: int = Field(default=20, ge=1)
    llm_model: str = "claude-sonnet-4-20250514"
    extract_biomarkers: bool = True
    extract_dose_rationale: bool = True


class T2FilterConfig(BaseModel):
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    generate_trial_design: bool = True
    trial_design_phase: str = "Phase_2"
    generate_competitive_landscape: bool = True
    llm_model: str = "claude-opus-4-20250514"
    max_dossier_length_tokens: int = Field(default=4000, ge=500)


class FiltersConfig(BaseModel):
    t0: T0FilterConfig = T0FilterConfig()
    t025: T025FilterConfig = T025FilterConfig()
    t1: T1FilterConfig = T1FilterConfig()
    t2: T2FilterConfig = T2FilterConfig()


# ---------------------------------------------------------------------------
# Target model
# ---------------------------------------------------------------------------

class PopulationContext(BaseModel):
    age_range: Optional[list[int]] = None
    exclude_conditions: list[str] = []


class TargetConfig(BaseModel):
    id: str
    disease_context: str
    description: str
    unmet_need: str
    pathway_ids: list[str] = []
    gene_set: dict[str, list[str]] = {}
    population_context: PopulationContext = PopulationContext()
    safety_exclusions: list[str] = []
    evidence_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    priority_mechanisms: list[str] = []

    @field_validator("pathway_ids")
    @classmethod
    def at_least_one_pathway(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("target.pathway_ids must contain at least one pathway ID")
        return v


# ---------------------------------------------------------------------------
# Drug universe
# ---------------------------------------------------------------------------

class DrugUniverseConfig(BaseModel):
    sources: list[str] = ["drugbank", "chembl", "fda_approved"]
    drug_types: list[str] = ["small_molecule"]
    status_filter: list[str] = ["approved", "investigational_phase2+"]
    exclude_indications: list[str] = []
    include_shelved: bool = True


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

class ComputeConfig(BaseModel):
    workers: int = Field(default=8, ge=1)
    llm_workers: int = Field(default=3, ge=1)
    batch_size: int = Field(default=1000, ge=1)
    llm_rate_limit_rpm: int = Field(default=50, ge=1)
    checkpoint_interval: int = Field(default=100, ge=1)
    cache_llm_responses: bool = True


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

class OutputConfig(BaseModel):
    db_path: str = "repurposing.db"
    receipts_dir: str = "receipts/"
    results_dir: str = "results/"
    top_n: int = Field(default=30, ge=1)
    export_dossiers: bool = True
    export_evidence_table: bool = True


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    name: str
    application: str = "drug_repurposing"
    description: str = ""
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

class PipelineConfig(BaseModel):
    project: ProjectConfig
    target: TargetConfig
    drug_universe: DrugUniverseConfig = DrugUniverseConfig()
    filters: FiltersConfig = FiltersConfig()
    compute: ComputeConfig = ComputeConfig()
    output: OutputConfig = OutputConfig()

    @model_validator(mode="after")
    def validate_llm_workers_not_exceed_workers(self) -> "PipelineConfig":
        if self.compute.llm_workers > self.compute.workers:
            raise ValueError("compute.llm_workers cannot exceed compute.workers")
        return self


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a repurposing pipeline config YAML")
    parser.add_argument("--validate", required=True, metavar="CONFIG_PATH")
    args = parser.parse_args()

    raw: dict[str, Any] = yaml.safe_load(Path(args.validate).read_text())
    try:
        config = PipelineConfig(**raw)
        print(f"Config valid: {config.project.name} / target={config.target.id}")
    except Exception as exc:
        print(f"Config invalid: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
