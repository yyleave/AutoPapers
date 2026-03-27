from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_papers_aminer_search_fails_without_api_key(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    r = CliRunner().invoke(app, ["papers", "aminer-search", "-q", "machine learning"])
    assert r.exit_code == 1
    text = r.stderr.strip()
    start, end = text.find("{"), text.rfind("}") + 1
    assert start >= 0 and end > start
    body = json.loads(text[start:end])
    assert body["ok"] is False
    assert body["error"] == "aminer_setup"


def test_papers_aminer_search_mocked_provider(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    from autopapers.providers.base import PaperRef
    from autopapers.providers.registry import ProviderRegistry

    class _FakeAminer:
        name = "aminer"

        def search(self, *, query: str, limit: int = 5):
            return [
                PaperRef(source="aminer", id="pid1", title="T1", pdf_url=None),
            ]

        def fetch_pdf(self, *, ref, dest_dir):
            dest_dir.mkdir(parents=True, exist_ok=True)
            p = dest_dir / "pid1.pdf"
            p.write_bytes(b"%PDF")
            return p

    reg = ProviderRegistry.default()
    merged = {**reg.providers, "aminer": _FakeAminer()}
    fake_reg = ProviderRegistry(providers=merged)

    monkeypatch.setattr(
        ProviderRegistry,
        "default",
        classmethod(lambda cls: fake_reg),
    )

    r = CliRunner().invoke(
        app,
        ["papers", "aminer-search", "-q", "q", "--download-first"],
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out[0]["id"] == "pid1"
    assert "fetch_metadata" in r.stderr
