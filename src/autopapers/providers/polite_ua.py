from __future__ import annotations

import os

_PROJECT_URL = "https://github.com/yyleave/AutoPapers"


def polite_mailto() -> str | None:
    """
    Contact mail for polite API use: ``AUTOPAPERS_MAILTO``, else ``OPENALEX_MAILTO``,
    else ``CROSSREF_MAILTO``.
    """

    for key in ("AUTOPAPERS_MAILTO", "OPENALEX_MAILTO", "CROSSREF_MAILTO"):
        m = os.environ.get(key, "").strip()
        if m:
            return m
    return None


def polite_user_agent(*, context: str) -> str:
    """
    User-Agent string for HTTP APIs. ``context`` labels the call site (e.g. ``openalex``).
    """

    mail = polite_mailto()
    if mail:
        return f"AutoPapers/0.1 (mailto:{mail})"
    return f"AutoPapers/0.1 (+{_PROJECT_URL}; {context})"
