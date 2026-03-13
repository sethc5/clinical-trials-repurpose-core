"""
receipt_system.py — JSON receipt writing + LLM cost tracking.

Every pipeline batch writes a receipt to receipts/ so that:
- Distributed runs can be merged
- LLM API spend is tracked per batch
- Run provenance is fully auditable

Receipt files: receipts/receipt_{machine_id}_{timestamp}.json
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _machine_id() -> str:
    """Best-effort stable machine identifier."""
    try:
        return socket.gethostname()
    except Exception:
        return platform.node() or "unknown"


class ReceiptSystem:
    def __init__(self, receipts_dir: str | Path) -> None:
        self.receipts_dir = Path(receipts_dir)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.machine_id = _machine_id()

    def write(
        self,
        batch_start: float,
        n_pairs_processed: int,
        n_llm_calls: int,
        llm_cost_usd: float,
        status: str = "completed",
        extra: dict | None = None,
    ) -> Path:
        """Write a receipt JSON and return its path."""
        now = time.time()
        receipt_id = str(uuid.uuid4())
        receipt = {
            "receipt_id": receipt_id,
            "machine_id": self.machine_id,
            "batch_start": datetime.fromtimestamp(batch_start, tz=timezone.utc).isoformat(),
            "batch_end": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "duration_seconds": round(now - batch_start, 2),
            "n_pairs_processed": n_pairs_processed,
            "n_llm_calls": n_llm_calls,
            "llm_cost_usd": round(llm_cost_usd, 4),
            "status": status,
            **(extra or {}),
        }

        timestamp = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"receipt_{self.machine_id}_{timestamp}_{receipt_id[:8]}.json"
        filepath = self.receipts_dir / filename
        filepath.write_text(json.dumps(receipt, indent=2))
        return filepath

    def load_all(self) -> list[dict]:
        """Load all receipt JSON files from receipts_dir."""
        receipts = []
        for f in sorted(self.receipts_dir.glob("receipt_*.json")):
            try:
                receipts.append(json.loads(f.read_text()))
            except Exception:
                pass
        return receipts

    def summarize(self) -> dict:
        """Aggregate stats across all receipts."""
        receipts = self.load_all()
        return {
            "n_receipts": len(receipts),
            "n_pairs_total": sum(r.get("n_pairs_processed", 0) for r in receipts),
            "n_llm_calls_total": sum(r.get("n_llm_calls", 0) for r in receipts),
            "llm_cost_usd_total": round(sum(r.get("llm_cost_usd", 0) for r in receipts), 4),
            "machines": list({r.get("machine_id") for r in receipts}),
        }
