from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_apply_openrouter_profile_ultra_cheap() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "apply_openrouter_profile.py"
    cfg = repo_root / "configs" / "openrouter_budget_profiles.yaml"
    proc = subprocess.run(
        [sys.executable, str(script), "--config", str(cfg), "--profile", "ultra_cheap"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "OPENROUTER_MODEL=google/gemini-2.0-flash-lite-001" in proc.stdout
    assert "OPENROUTER_PROVIDER_SORT=price" in proc.stdout
    assert "OPENROUTER_ZDR=true" in proc.stdout
