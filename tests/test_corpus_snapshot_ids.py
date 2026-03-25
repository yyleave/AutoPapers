from __future__ import annotations

from autopapers.phase1.corpus_snapshot import _paper_node_id, _query_node_id


def test_paper_node_id_shape() -> None:
    assert _paper_node_id("arxiv", "2501.00001") == "paper:arxiv:2501.00001"


def test_query_node_id_normalizes_whitespace() -> None:
    a = _query_node_id("  deep   learning  ")
    b = _query_node_id("deep learning")
    assert a == b
    assert a.startswith("query:")
