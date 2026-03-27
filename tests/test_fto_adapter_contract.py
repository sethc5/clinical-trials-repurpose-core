from __future__ import annotations

from adapters import fto_adapter


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_check_fto_sends_versioned_repurposing_payload(monkeypatch):
    captured: dict = {}

    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp(
            {
                "risk_level": "MEDIUM",
                "blocking_patents": [],
                "clear_territories": ["US"],
                "design_around_suggestions": [],
                "api_version": "1.1",
                "contract_version": "fto.v1",
                "service": "patent-fto-core",
                "client_ref": "PAIR1",
                "cached": False,
            }
        )

    monkeypatch.setattr(fto_adapter.requests, "post", _fake_post)
    result = fto_adapter.check_fto(
        drug_name="DrugA",
        indication="Rare disease",
        smiles="CCO",
        client_ref="PAIR1",
    )

    assert captured["json"]["api_version"] == "1.1"
    assert captured["json"]["client_repo"] == "clinical-trials-repurpose-core"
    assert captured["json"]["use_type"] == "repurposed_indication"
    assert captured["json"]["client_ref"] == "PAIR1"
    assert result.contract_version == "fto.v1"
    assert result.client_ref == "PAIR1"


def test_check_fto_contract_fields_fallback(monkeypatch):
    def _fake_post(url, json, timeout):
        return _Resp(
            {
                "risk_level": "LOW",
                "blocking_patents": [],
                "clear_territories": ["US"],
                "design_around_suggestions": [],
                "cached": True,
            }
        )

    monkeypatch.setattr(fto_adapter.requests, "post", _fake_post)
    result = fto_adapter.check_fto(drug_name="DrugA", indication="X")

    assert result.api_version == "1.1"
    assert result.contract_version == "fto.v1"
    assert result.service == "patent-fto-core"
