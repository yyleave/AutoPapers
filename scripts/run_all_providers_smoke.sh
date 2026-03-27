#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "== AutoPapers provider smoke =="
echo "repo: $REPO_ROOT"
echo "This script runs optional network-marked provider tests."

export AUTOPAPERS_NETWORK_SMOKE=1

uv run pytest -q -m network \
  tests/test_papers_arxiv_provider.py::test_arxiv_search_returns_results \
  tests/test_openalex_provider.py::test_openalex_search_network_smoke \
  tests/test_crossref_provider.py::test_crossref_search_network_smoke \
  tests/test_aminer_provider_search.py::test_aminer_search_network_smoke
