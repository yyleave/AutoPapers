from __future__ import annotations

from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def test_run_debate_stub_has_three_roles() -> None:
    d = run_debate_stub(profile_summary="p" * 300, corpus_summary="c" * 300)
    assert set(d) == {"radical", "conservative", "killer"}
    assert "HypothesisAgent" in d["radical"]
    assert "SanityAgent" in d["conservative"]
    assert "KillerAgent" in d["killer"]


def test_merge_stub_to_proposal_passes_status_and_debate_notes() -> None:
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="My title", debate=debate, status="confirmed")
    assert prop["title"] == "My title"
    assert prop["status"] == "confirmed"
    assert prop["debate_notes"] == debate
    assert prop["schema_version"] == "0.1"
