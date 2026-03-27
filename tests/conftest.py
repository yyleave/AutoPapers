from __future__ import annotations

import pytest

from autopapers import cli
from autopapers.phase2.debate import run_debate_stub


@pytest.fixture(autouse=True)
def _stub_debate_for_offline_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "run_debate",
        lambda *, profile_summary, corpus_summary: run_debate_stub(
            profile_summary=profile_summary,
            corpus_summary=corpus_summary,
        ),
    )
