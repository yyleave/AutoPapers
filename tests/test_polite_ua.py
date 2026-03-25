from __future__ import annotations

import pytest

from autopapers.providers.polite_ua import polite_mailto, polite_user_agent


def test_polite_user_agent_uses_autopapers_mailto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_MAILTO", raising=False)
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    monkeypatch.setenv("AUTOPAPERS_MAILTO", "a@b.c")
    ua = polite_user_agent(context="test")
    assert "mailto:a@b.c" in ua
    assert polite_mailto() == "a@b.c"


def test_polite_mailto_fallback_openalex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_MAILTO", raising=False)
    monkeypatch.setenv("OPENALEX_MAILTO", "o@x.y")
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    assert polite_mailto() == "o@x.y"
    assert "mailto:o@x.y" in polite_user_agent(context="x")


def test_polite_mailto_fallback_crossref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_MAILTO", raising=False)
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    monkeypatch.setenv("CROSSREF_MAILTO", "c@r.f")
    assert polite_mailto() == "c@r.f"
    assert "mailto:c@r.f" in polite_user_agent(context="crossref")


def test_polite_user_agent_without_mailto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_MAILTO", raising=False)
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    ua = polite_user_agent(context="test")
    assert "AutoPapers" in ua
    assert "github.com" in ua
