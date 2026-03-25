from __future__ import annotations

import autopapers


def test_package_version_is_non_empty() -> None:
    assert isinstance(autopapers.__version__, str)
    assert autopapers.__version__.strip() != ""
