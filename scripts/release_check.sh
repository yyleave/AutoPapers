#!/usr/bin/env bash
set -euo pipefail

WITH_NETWORK_SMOKE=0
SKIP_OFFLINE_TESTS=0
SKIP_DEMO_TESTS=0
LEGACY_ONLY_TESTS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-network-smoke)
      WITH_NETWORK_SMOKE=1
      shift
      ;;
    --skip-offline-tests)
      SKIP_OFFLINE_TESTS=1
      shift
      ;;
    --skip-demo-tests)
      SKIP_DEMO_TESTS=1
      shift
      ;;
    --legacy-only-tests)
      LEGACY_ONLY_TESTS=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/release_check.sh [--with-network-smoke] [--skip-offline-tests] [--skip-demo-tests] [--legacy-only-tests]

Pre-release acceptance checklist:
  1) Lint critical codepaths + autopapers doctor (environment snapshot)
  2) Run full offline test suite
  3) Run demo + legacy script integration tests
  4) (Optional) Run provider network smoke tests

Options:
  --with-network-smoke   Also run scripts/run_all_providers_smoke.sh
  --skip-offline-tests   Skip pytest -m "not network" stage
  --skip-demo-tests      Skip tests/test_demo_scripts.py stage
  --legacy-only-tests    In stage 3, run only tests/test_paper_fetcher_cli.py
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "== AutoPapers release check =="
echo "repo: $REPO_ROOT"

echo
echo "[1/4] Ruff checks + autopapers doctor"
uv run ruff check .
uv run autopapers doctor

echo
if [[ "$SKIP_OFFLINE_TESTS" -eq 1 ]]; then
  echo "[2/4] Offline regression (skipped)"
else
  echo "[2/4] Offline regression"
  uv run pytest -q -m "not network"
fi

echo
if [[ "$SKIP_DEMO_TESTS" -eq 1 ]]; then
  echo "[3/4] Demo + legacy scripts integration (skipped)"
else
  if [[ "$LEGACY_ONLY_TESTS" -eq 1 ]]; then
    echo "[3/4] Demo + legacy scripts integration (legacy-only)"
    uv run pytest -q tests/test_paper_fetcher_cli.py
  else
    echo "[3/4] Demo + legacy scripts integration"
    uv run pytest -q tests/test_demo_scripts.py tests/test_paper_fetcher_cli.py
  fi
fi

if [[ "$WITH_NETWORK_SMOKE" -eq 1 ]]; then
  echo
  echo "[4/4] Provider network smoke"
  scripts/run_all_providers_smoke.sh
else
  echo
  echo "[4/4] Provider network smoke (skipped)"
  echo "Use --with-network-smoke to enable."
fi

echo
echo "Release check passed."
