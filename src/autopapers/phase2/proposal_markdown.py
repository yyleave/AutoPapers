from __future__ import annotations

from typing import Any


def _bullet_list(items: list[Any] | None, *, empty: str = "_None._") -> str:
    if not items:
        return empty
    return "\n".join(f"- {x}" for x in items if x is not None)


def proposal_to_markdown(proposal: dict[str, Any]) -> str:
    """
    Render a research proposal dict (same shape as research_proposal.schema.json) as Markdown.
    """

    title = str(proposal.get("title") or "Research proposal")
    status = proposal.get("status", "")
    schema_v = proposal.get("schema_version", "")

    blocks: list[str] = [
        f"# {title}",
        "",
        f"- **Status:** {status}",
        f"- **Schema version:** {schema_v}",
        "",
        "## Problem",
        "",
        str(proposal.get("problem") or ""),
        "",
        "## Hypothesis",
        "",
        str(proposal.get("hypothesis") or ""),
        "",
        "## Contributions",
        "",
        _bullet_list(proposal.get("contributions")),
        "",
        "## Baselines",
        "",
        _bullet_list(proposal.get("baselines")),
        "",
        "## Risks",
        "",
        _bullet_list(proposal.get("risks")),
        "",
        "## Resources",
        "",
        _bullet_list(proposal.get("resources")),
        "",
    ]

    dn = proposal.get("debate_notes")
    if isinstance(dn, dict) and dn:
        blocks.extend(["## Debate notes", ""])
        for role, text in dn.items():
            blocks.extend([f"### {role}", "", str(text), ""])

    return "\n".join(blocks).rstrip() + "\n"
