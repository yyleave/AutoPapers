from __future__ import annotations

from pathlib import Path

from autopapers.config import Paths

DEFAULT_SNAPSHOT = "corpus-snapshot.json"
MAX_CHARS = 20_000


def load_corpus_text_for_proposal(
    paths: Paths,
    corpus: Path | None,
) -> tuple[str, Path | None]:
    """
    Resolve corpus text for proposal drafting.

    If ``corpus`` is given, read that file. Otherwise use
    ``paths.kg_dir / corpus-snapshot.json`` when it exists.
    """
    if corpus is not None:
        text = corpus.read_text(encoding="utf-8")
        return text[:MAX_CHARS], corpus

    default = paths.kg_dir / DEFAULT_SNAPSHOT
    if default.is_file():
        text = default.read_text(encoding="utf-8")
        return text[:MAX_CHARS], default

    return "", None
