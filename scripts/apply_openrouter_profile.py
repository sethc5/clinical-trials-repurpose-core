#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "openrouter_budget_profiles.yaml"


def _load(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return raw


def _profile_env(raw: dict, profile: str) -> dict[str, str]:
    profiles = raw.get("profiles") or {}
    if not isinstance(profiles, dict) or profile not in profiles:
        raise ValueError(f"profile not found: {profile}")
    cfg = profiles[profile] or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"profile {profile} must be mapping")

    provider = cfg.get("provider") or {}
    if not isinstance(provider, dict):
        raise ValueError(f"profile {profile}.provider must be mapping")

    out: dict[str, str] = {}
    model = str(cfg.get("openrouter_model") or "").strip()
    if model:
        out["OPENROUTER_MODEL"] = model

    fbs = cfg.get("openrouter_fallback_models") or []
    if not isinstance(fbs, list):
        raise ValueError(f"profile {profile}.openrouter_fallback_models must be list")
    fallback_items = [str(x).strip() for x in fbs if str(x).strip()]
    if fallback_items:
        out["OPENROUTER_FALLBACK_MODELS"] = ",".join(fallback_items)

    sort = str(provider.get("sort") or "").strip()
    if sort:
        out["OPENROUTER_PROVIDER_SORT"] = sort

    allow_fallbacks = provider.get("allow_fallbacks")
    if isinstance(allow_fallbacks, bool):
        out["OPENROUTER_ALLOW_FALLBACKS"] = "true" if allow_fallbacks else "false"

    require_parameters = provider.get("require_parameters")
    if isinstance(require_parameters, bool):
        out["OPENROUTER_REQUIRE_PARAMETERS"] = "true" if require_parameters else "false"

    data_collection = str(provider.get("data_collection") or "").strip()
    if data_collection:
        out["OPENROUTER_DATA_COLLECTION"] = data_collection

    zdr = provider.get("zdr")
    if isinstance(zdr, bool):
        out["OPENROUTER_ZDR"] = "true" if zdr else "false"

    only = provider.get("only")
    if isinstance(only, list) and only:
        out["OPENROUTER_ONLY_PROVIDERS"] = ",".join(str(x).strip() for x in only if str(x).strip())

    ignore = provider.get("ignore")
    if isinstance(ignore, list) and ignore:
        out["OPENROUTER_IGNORE_PROVIDERS"] = ",".join(str(x).strip() for x in ignore if str(x).strip())

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Print OpenRouter environment exports for a named budget profile.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--format", choices=("bash", "env"), default="bash")
    args = parser.parse_args()

    raw = _load(args.config)
    env_map = _profile_env(raw, args.profile)
    for key, value in env_map.items():
        if args.format == "bash":
            print(f"export {key}={value}")
        else:
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
