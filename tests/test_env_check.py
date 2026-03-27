from __future__ import annotations

import pytest

from autopapers.env_check import build_llm_backend_diagnostics


def test_build_llm_backend_diagnostics_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_LLM_BACKEND", raising=False)
    d = build_llm_backend_diagnostics()
    assert d["effective_backend"] == "openai"
    assert d["backend_valid"] is True
    assert d["backend_hint"] is None
    assert d["supported_backends"] == ["openai", "ollama", "stub"]


def test_build_llm_backend_diagnostics_invalid_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_LLM_BACKEND", "invalid")
    d = build_llm_backend_diagnostics()
    assert d["effective_backend"] == "invalid"
    assert d["backend_valid"] is False
    assert d["backend_hint"] == "Set AUTOPAPERS_LLM_BACKEND to openai|ollama|stub"
