"""
batch_runner.py — Distributed batch launcher.

Splits the drug × indication pair space into chunks and dispatches them
to worker processes (local) or remote compute nodes (SSH / SLURM).

Usage:
    python batch_runner.py --config config.yaml --n-chunks 4
    python batch_runner.py --config config.yaml --chunk-id 0 --n-chunks 4  # single chunk
"""

from __future__ import annotations

import argparse
import logging
import math
import subprocess
import sys
from pathlib import Path

import yaml

from config_schema import PipelineConfig
from db_utils import RepurposingDB

log = logging.getLogger(__name__)


def chunk_pairs(pairs: list[dict], n_chunks: int) -> list[list[dict]]:
    chunk_size = math.ceil(len(pairs) / n_chunks)
    return [pairs[i : i + chunk_size] for i in range(0, len(pairs), chunk_size)]


def run_chunk(config_path: str, chunk_id: int, n_chunks: int, tier: str = "2") -> int:
    """Spawn a pipeline_core subprocess for a specific chunk."""
    cmd = [
        sys.executable, "pipeline_core.py",
        "--config", config_path,
        "--tier", tier,
        "--chunk-id", str(chunk_id),
        "--n-chunks", str(n_chunks),
    ]
    log.info(f"Launching chunk {chunk_id}/{n_chunks}: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Distributed batch launcher")
    parser.add_argument("--config", required=True)
    parser.add_argument("--n-chunks", type=int, default=4)
    parser.add_argument("--chunk-id", type=int, default=None,
                        help="Run only this chunk (for remote dispatch)")
    parser.add_argument("--tier", default="2")
    args = parser.parse_args()

    raw = yaml.safe_load(Path(args.config).read_text())
    config = PipelineConfig(**raw)
    db = RepurposingDB(config.output.db_path)
    pairs = db.get_all_drug_indication_pairs()
    chunks = chunk_pairs(pairs, args.n_chunks)
    log.info(f"Total pairs: {len(pairs)} → {len(chunks)} chunks of ~{len(chunks[0])} each")

    if args.chunk_id is not None:
        # Single chunk mode (called from remote node)
        rc = run_chunk(args.config, args.chunk_id, args.n_chunks, args.tier)
        raise SystemExit(rc)

    # Local multi-process dispatch
    failed = []
    for i in range(len(chunks)):
        rc = run_chunk(args.config, i, args.n_chunks, args.tier)
        if rc != 0:
            log.error(f"Chunk {i} failed with exit code {rc}")
            failed.append(i)

    if failed:
        log.error(f"Failed chunks: {failed}")
        raise SystemExit(1)
    log.info("All chunks complete.")


if __name__ == "__main__":
    main()
