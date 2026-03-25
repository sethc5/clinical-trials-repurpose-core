from __future__ import annotations

import llm_client


def test_build_extra_body_empty_by_default(monkeypatch) -> None:
    for key in (
        "OPENROUTER_PROVIDER_SORT",
        "OPENROUTER_ALLOW_FALLBACKS",
        "OPENROUTER_REQUIRE_PARAMETERS",
        "OPENROUTER_DATA_COLLECTION",
        "OPENROUTER_ZDR",
        "OPENROUTER_ONLY_PROVIDERS",
        "OPENROUTER_IGNORE_PROVIDERS",
        "OPENROUTER_FALLBACK_MODELS",
    ):
        monkeypatch.delenv(key, raising=False)
    assert llm_client._build_extra_body() == {}


def test_build_extra_body_budget_profile(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_PROVIDER_SORT", "price")
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_REQUIRE_PARAMETERS", "true")
    monkeypatch.setenv("OPENROUTER_DATA_COLLECTION", "deny")
    monkeypatch.setenv("OPENROUTER_ZDR", "true")
    monkeypatch.setenv("OPENROUTER_ONLY_PROVIDERS", "openai, azure")
    monkeypatch.setenv("OPENROUTER_IGNORE_PROVIDERS", "deepinfra")
    monkeypatch.setenv(
        "OPENROUTER_FALLBACK_MODELS",
        "google/gemini-2.0-flash-001,qwen/qwen3.5-flash-02-23",
    )

    body = llm_client._build_extra_body()
    assert body["provider"]["sort"] == "price"
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["require_parameters"] is True
    assert body["provider"]["data_collection"] == "deny"
    assert body["provider"]["zdr"] is True
    assert body["provider"]["only"] == ["openai", "azure"]
    assert body["provider"]["ignore"] == ["deepinfra"]
    assert body["models"] == [
        "google/gemini-2.0-flash-001",
        "qwen/qwen3.5-flash-02-23",
    ]


def test_resolve_model_maps_anthropic_name(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    out = llm_client._resolve_model("claude-sonnet-4-20250514")
    assert out == "anthropic/claude-sonnet-4"
