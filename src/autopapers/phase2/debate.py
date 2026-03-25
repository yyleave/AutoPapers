from __future__ import annotations


def run_debate_stub(*, profile_summary: str, corpus_summary: str) -> dict[str, str]:
    """
    Placeholder debate: returns fixed-role strings for wiring Phase 2 orchestration.

    Replace with LLM-backed agents later.
    """
    return {
        "radical": (
            f"[HypothesisAgent] Propose a bold extension based on: {profile_summary[:200]}..."
        ),
        "conservative": (
            "[SanityAgent] Check feasibility: scope, compute, data availability; "
            "flag overstated claims."
        ),
        "killer": (
            "[KillerAgent] Reviewer attack: missing baselines, unclear contribution, "
            f"weak experimental design vs corpus: {corpus_summary[:200]}..."
        ),
    }


def merge_stub_to_proposal(
    *,
    title: str,
    debate: dict[str, str],
    status: str = "draft",
) -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "title": title,
        "problem": "Derived from profile keywords / problem statements (fill manually).",
        "hypothesis": debate["radical"][:500],
        "contributions": [
            "TBD: primary empirical or theoretical contribution",
        ],
        "baselines": ["TBD: standard baselines in the field"],
        "risks": [
            debate["killer"][:300],
            "Compute / data access",
        ],
        "resources": ["Corpus paths under data/papers/"],
        "debate_notes": debate,
        "status": status,
    }
