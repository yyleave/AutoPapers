from __future__ import annotations

from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub
from autopapers.phase2.proposal_markdown import proposal_to_markdown


def test_proposal_to_markdown_empty_lists_use_placeholder() -> None:
    md = proposal_to_markdown(
        {
            "title": "T",
            "schema_version": "0.1",
            "status": "draft",
            "problem": "p",
            "hypothesis": "h",
            "contributions": [],
            "baselines": [],
            "risks": [],
            "resources": [],
        }
    )
    assert md.count("_None._") >= 4


def test_proposal_to_markdown_filters_none_list_items() -> None:
    md = proposal_to_markdown(
        {
            "title": "T",
            "contributions": [None, "keep"],
            "baselines": ["b"],
            "risks": [],
            "resources": [],
        }
    )
    assert "- keep" in md
    assert md.count("- None") == 0


def test_proposal_to_markdown_skips_non_dict_debate_notes() -> None:
    md = proposal_to_markdown({"title": "T", "debate_notes": "not-a-dict"})
    assert "## Debate notes" not in md


def test_proposal_to_markdown_includes_sections() -> None:
    debate = run_debate_stub(profile_summary="{}", corpus_summary="{}")
    prop = merge_stub_to_proposal(title="My study", debate=debate, status="draft")
    md = proposal_to_markdown(prop)
    assert "# My study" in md
    assert "## Problem" in md
    assert "## Hypothesis" in md
    assert "## Debate notes" in md
    assert "**Status:** draft" in md
