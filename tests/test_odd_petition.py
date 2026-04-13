from __future__ import annotations

from last_mile import odd_petition


def test_generate_plausibility_uses_drug_id_fallback(monkeypatch):
    monkeypatch.setattr(odd_petition.llm_client, "complete", lambda _prompt: "ok")

    text = odd_petition._generate_plausibility(
        drug={"drug_id": "DB99999", "mechanism_of_action": "demo moa"},
        indication={"indication_id": "rare_x", "name": "Rare X"},
        run={"t2_evidence_summary": "summary"},
        evidence_items=[],
    )
    assert text == "ok"

