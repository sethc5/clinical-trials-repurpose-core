"""fto_adapter.py — HTTP client for the patent-fto-core FTO analysis service.

For drug repurposing, the FTO risk profile differs from new chemical entities:
  - Composition-of-matter patents on the drug itself are usually expired or
    about to expire (that's why repurposing is attractive).
  - The live risk is METHOD-OF-USE patents covering the new indication.
  - Hatch-Waxman § 505(b)(2) carve-outs apply if the new indication is
    genuinely differentiated from the patented use.

Usage in pipeline_core.py:
    from adapters.fto_adapter import check_fto, FTOResult

    fto = check_fto(
        drug_name=drug["name"],
        indication=indication["name"],
        smiles=drug.get("smiles"),
    )
    if fto.risk_level == "HIGH":
        log.warning("%s → %s: HIGH FTO risk (%d blocking patents)",
                    drug["name"], indication["name"], len(fto.blocking_patents))

Environment variables:
    FTO_SERVICE_URL  — base URL of the FTO service (default: http://localhost:8010)
    FTO_TIMEOUT      — request timeout in seconds (default: 120)

If the FTO service is unavailable, check_fto() returns FTOResult with
risk_level="UNKNOWN" and logs a warning rather than raising.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

_FTO_URL = os.environ.get("FTO_SERVICE_URL", "http://localhost:8010")
_TIMEOUT = int(os.environ.get("FTO_TIMEOUT", "120"))
_API_VERSION = os.environ.get("FTO_API_VERSION", "1.1")
_SUPPORTED_CONTRACTS = {"fto.v1"}


@dataclass
class FTOResult:
    risk_level: str                        # "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
    drug_name: str = ""
    indication: str = ""
    blocking_patents: list[dict] = field(default_factory=list)
    method_of_use_risk: str = "UNKNOWN"    # specific risk on method-of-use claims
    carve_out_possible: bool = False       # True if § 505(b)(2) labeling carve-out applies
    clear_territories: list[str] = field(default_factory=list)
    design_around_suggestions: list[str] = field(default_factory=list)
    api_version: str = _API_VERSION
    contract_version: str = "fto.v1"
    service: str = "patent-fto-core"
    client_ref: str | None = None
    cached: bool = False
    error: str | None = None              # set when service is unavailable


_UNAVAILABLE = FTOResult(risk_level="UNKNOWN", error="FTO service unavailable")


def check_fto(
    drug_name: str,
    indication: str,
    smiles: str | None = None,
    jurisdictions: list[str] | None = None,
    client_ref: str | None = None,
    use_cache: bool = True,
) -> FTOResult:
    """Call the FTO service for a drug repurposing candidate.

    For repurposing, use_type is always "repurposed_indication" — the service
    focuses on method-of-use claims rather than composition-of-matter claims.

    Returns an ``FTOResult`` with ``risk_level="UNKNOWN"`` if the service is
    unreachable — callers should log and continue rather than raising.
    """
    if jurisdictions is None:
        jurisdictions = ["US"]

    payload: dict = {
        "api_version": _API_VERSION,
        "client_repo": "clinical-trials-repurpose-core",
        "drug_name": drug_name,
        "indication": indication,
        "use_type": "repurposed_indication",
        "client_ref": client_ref,
        "jurisdictions": jurisdictions,
        "use_cache": use_cache,
    }
    if smiles:
        payload["smiles"] = smiles

    try:
        resp = requests.post(
            f"{_FTO_URL}/fto/compound",
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        d = resp.json()
        contract_version = d.get("contract_version") or ""
        if contract_version and contract_version not in _SUPPORTED_CONTRACTS:
            log.warning(
                "FTO response contract mismatch: expected %s got %s",
                sorted(_SUPPORTED_CONTRACTS),
                contract_version,
            )
        return FTOResult(
            risk_level=d["risk_level"],
            drug_name=drug_name,
            indication=indication,
            blocking_patents=d.get("blocking_patents", []),
            method_of_use_risk=d.get("method_of_use_risk", d["risk_level"]),
            carve_out_possible=d.get("carve_out_possible", False),
            clear_territories=d.get("clear_territories", []),
            design_around_suggestions=d.get("design_around_suggestions", []),
            api_version=d.get("api_version", _API_VERSION),
            contract_version=d.get("contract_version", "fto.v1"),
            service=d.get("service", "patent-fto-core"),
            client_ref=d.get("client_ref"),
            cached=d.get("cached", False),
        )
    except requests.exceptions.ConnectionError:
        log.warning(
            "FTO service unreachable at %s — skipping FTO check for %r → %r",
            _FTO_URL, drug_name, indication,
        )
        return FTOResult(risk_level="UNKNOWN", drug_name=drug_name,
                         indication=indication, error="connection refused")
    except requests.exceptions.Timeout:
        log.warning("FTO service timed out after %ds for %r → %r", _TIMEOUT, drug_name, indication)
        return FTOResult(risk_level="UNKNOWN", drug_name=drug_name,
                         indication=indication, error="timeout")
    except requests.exceptions.HTTPError as exc:
        log.warning("FTO service HTTP error for %r → %r: %s", drug_name, indication, exc)
        return FTOResult(risk_level="UNKNOWN", drug_name=drug_name,
                         indication=indication, error=str(exc))
    except Exception as exc:
        log.exception("Unexpected error calling FTO service for %r → %r", drug_name, indication)
        return FTOResult(risk_level="UNKNOWN", drug_name=drug_name,
                         indication=indication, error=str(exc))


def is_fto_service_available() -> bool:
    """Quick health-check: return True if the FTO service is up."""
    try:
        resp = requests.get(f"{_FTO_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
