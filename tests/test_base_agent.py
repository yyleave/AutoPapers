from __future__ import annotations

import pytest

from autopapers.agents.base import BaseAgent


def test_base_agent_run_not_implemented() -> None:
    a = BaseAgent(name="n", role="r")
    with pytest.raises(NotImplementedError):
        a.run({})
