from __future__ import annotations

from pathlib import Path


def src_dir() -> Path:
    """Directory containing both `autopapers` package and legacy `api` (`src/`)."""
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    """Repository root (parent of `src/`)."""
    return src_dir().parent


def ensure_legacy_api_on_path() -> None:
    """Allow `import api` when running from an editable install."""
    import sys

    s = str(src_dir())
    if s not in sys.path:
        sys.path.insert(0, s)
