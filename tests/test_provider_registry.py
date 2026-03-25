from __future__ import annotations

import pytest

from autopapers.providers.registry import ProviderRegistry


def test_default_registry_has_expected_providers() -> None:
    reg = ProviderRegistry.default()
    names = set(reg.providers.keys())
    assert names == {"aminer", "arxiv", "crossref", "local_pdf", "openalex"}


def test_registry_get_returns_provider() -> None:
    reg = ProviderRegistry.default()
    assert reg.get("arxiv").name == "arxiv"


def test_registry_get_unknown_lists_options() -> None:
    reg = ProviderRegistry.default()
    with pytest.raises(KeyError, match="Unknown provider: nosuch"):
        reg.get("nosuch")
