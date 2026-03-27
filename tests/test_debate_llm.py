from __future__ import annotations

import pytest

from autopapers.phase2.debate import load_llm_config, run_debate


def test_load_llm_config_reads_ollama_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_LLM_BACKEND", "ollama")
    monkeypatch.setenv("AUTOPAPERS_OLLAMA_MODEL", "llama3.2:3b")
    cfg = load_llm_config()
    assert cfg.backend == "ollama"
    assert cfg.model == "llama3.2:3b"


def test_run_debate_openai_without_key_has_setup_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_LLM_BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError) as ei:
        run_debate(profile_summary="p", corpus_summary="c")
    msg = str(ei.value)
    assert "OPENAI_API_KEY" in msg
    assert "AUTOPAPERS_LLM_BACKEND=openai" in msg
