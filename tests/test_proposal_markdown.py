from __future__ import annotations

from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub
from autopapers.phase2.proposal_markdown import proposal_to_markdown


def test_proposal_to_markdown_includes_sections() -> None:
    debate = run_debate_stub(profile_summary="{}", corpus_summary="{}")
    prop = merge_stub_to_proposal(title="My study", debate=debate, status="draft")
    md = proposal_to_markdown(prop)
    assert "# My study" in md
    assert "## Problem" in md
    assert "## Hypothesis" in md
    assert "## Debate notes" in md
    assert "**Status:** draft" in md
