from __future__ import annotations

from autopapers.logging_utils import setup_logging


def test_setup_logging_accepts_known_level() -> None:
    setup_logging(level="WARNING")


def test_setup_logging_unknown_level_falls_back() -> None:
    # getattr(logging, "NOTALEVEL", INFO) -> INFO
    setup_logging(level="NOTALEVEL")
