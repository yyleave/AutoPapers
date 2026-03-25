from __future__ import annotations

from pathlib import Path

from autopapers.phase1.profile.validate import load_schema, validate_profile
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def proposal_schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "autopapers"
        / "schemas"
        / "research_proposal.schema.json"
    )


def test_proposal_merged_stub_validates() -> None:
    schema = load_schema(proposal_schema_path())
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="T", debate=debate)
    validate_profile(profile=prop, schema=schema)
