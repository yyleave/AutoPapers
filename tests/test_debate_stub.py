from __future__ import annotations

from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def test_run_debate_stub_has_three_roles() -> None:
    d = run_debate_stub(profile_summary="p" * 300, corpus_summary="c" * 300)
    assert set(d) == {"radical", "conservative", "killer"}
    assert "HypothesisAgent" in d["radical"]
    assert "SanityAgent" in d["conservative"]
    assert "KillerAgent" in d["killer"]


def test_merge_truncates_long_conservative_in_problem() -> None:
    long_cons = "x" * 500
    debate = {
        "radical": "r",
        "conservative": long_cons,
        "killer": "k",
    }
    prop = merge_stub_to_proposal(title="T", debate=debate)
    prob = str(prop["problem"])
    assert prob.endswith("…")
    prefix = "Feasibility / scope (conservative): "
    assert prefix in prob
    tail = prob.split(prefix, 1)[1].strip()
    assert tail == "x" * 400 + "…"


def test_merge_truncates_long_killer_in_risks() -> None:
    long_kill = "z" * 400
    debate = {
        "radical": "r",
        "conservative": "c",
        "killer": long_kill,
    }
    prop = merge_stub_to_proposal(title="T", debate=debate)
    risks = prop["risks"]
    assert isinstance(risks, list)
    assert len(risks) >= 1
    assert "z" * 200 in risks[0]


def test_merge_truncates_long_radical_in_hypothesis() -> None:
    long_rad = "q" * 600
    debate = {
        "radical": long_rad,
        "conservative": "c",
        "killer": "k",
    }
    prop = merge_stub_to_proposal(title="T", debate=debate)
    assert str(prop["hypothesis"]).startswith("q" * 400)


def test_merge_stub_to_proposal_passes_status_and_debate_notes() -> None:
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="My title", debate=debate, status="confirmed")
    assert prop["title"] == "My title"
    assert prop["status"] == "confirmed"
    assert prop["debate_notes"] == debate
    assert prop["schema_version"] == "0.1"
    prob = str(prop["problem"])
    assert "Feasibility / scope (conservative):" in prob
    assert "SanityAgent" in prob
