#!/usr/bin/env bash
set -euo pipefail

MODE="offline"
WORKDIR=""
EXTENDED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --workdir)
      WORKDIR="${2:-}"
      shift 2
      ;;
    --extended)
      EXTENDED=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/mvp_demo.sh [--mode offline|hybrid] [--workdir /tmp/path] [--extended]

Runs the AutoPapers MVP end-to-end demo:
  profile -> phase1 run -> corpus -> proposal -> status
With --extended, also runs phase5 (orchestrated experiment -> bundle -> archive) + verify.

Modes:
  offline  Use local_pdf provider only (default).
  hybrid   Offline flow + optional network smoke tests.
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "offline" && "$MODE" != "hybrid" ]]; then
  echo "Invalid --mode: $MODE (expected offline|hybrid)" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "$WORKDIR" ]]; then
  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/autopapers-mvp-XXXXXX")"
fi
mkdir -p "$WORKDIR"

STEPS=7
if [[ "$EXTENDED" -eq 1 ]]; then STEPS=9; fi

echo "== AutoPapers MVP demo =="
echo "mode: $MODE"
echo "repo: $REPO_ROOT"
echo "workdir: $WORKDIR"
echo "extended: $EXTENDED (total steps: $STEPS)"

export AUTOPAPERS_REPO_ROOT="$WORKDIR"
export AUTOPAPERS_PROVIDER="local_pdf"
export AUTOPAPERS_LLM_BACKEND="${AUTOPAPERS_LLM_BACKEND:-stub}"

PDF_DIR="$WORKDIR/demo_pdfs"
PROFILE_JSON="$WORKDIR/user_profile.json"
mkdir -p "$PDF_DIR"
export PDF_DIR
export PROFILE_JSON

echo
echo "[1/$STEPS] Workspace config (configs/default.toml) + tiny local PDF fixture"
uv run autopapers workspace-init
uv run python - <<'PY'
from pathlib import Path
from pypdf import PdfWriter
import os

pdf = Path(os.environ["PDF_DIR"]) / "demo.pdf"
writer = PdfWriter()
writer.add_blank_page(width=72, height=72)
with pdf.open("wb") as f:
    writer.write(f)
print(str(pdf.resolve()))
PY

echo
echo "[2/$STEPS] Init profile and patch keywords to local PDF dir"
uv run autopapers profile init -o "$PROFILE_JSON"
uv run python - <<'PY'
import json
import os
from pathlib import Path

profile = Path(os.environ["PROFILE_JSON"])
pdf_dir = Path(os.environ["PDF_DIR"]).resolve()
doc = json.loads(profile.read_text(encoding="utf-8"))
doc["user"]["languages"] = ["zh", "en"]
doc["research_intent"]["keywords"] = [str(pdf_dir)]
profile.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(str(profile.resolve()))
PY

echo
echo "[3/$STEPS] Phase1 run (search + fetch-first + parse-fetched)"
uv run autopapers phase1 run \
  --profile "$PROFILE_JSON" \
  --limit 1 \
  --fetch-first \
  --parse-fetched \
  --parse-max-pages 1

echo
echo "[4/$STEPS] Build and inspect corpus snapshot"
uv run autopapers corpus build --profile "$PROFILE_JSON"
uv run autopapers corpus info
uv run autopapers corpus export-edges -o "$WORKDIR/edges.csv"
uv run autopapers corpus export-nodes -o "$WORKDIR/nodes.csv"

echo
echo "[5/$STEPS] Draft/confirm/export proposal"
uv run autopapers proposal draft --profile "$PROFILE_JSON" --title "MVP Demo Topic"
uv run autopapers proposal confirm -i "$WORKDIR/data/proposals/proposal-draft.json"
uv run autopapers proposal export -i "$WORKDIR/data/proposals/proposal-confirmed.json"

echo
echo "[6/$STEPS] Stage snapshot (status + flow)"
uv run autopapers status
uv run autopapers flow

if [[ "$EXTENDED" -eq 1 ]]; then
  echo
  echo "[7/$STEPS] Phase5 orchestration (experiment + manuscript + bundle + archive)"
  uv run autopapers phase5 run --proposal "$WORKDIR/data/proposals/proposal-confirmed.json"
  echo
  echo "[8/$STEPS] Phase5 verify (bundle vs archive)"
  uv run autopapers phase5 verify \
    --bundle-dir "$WORKDIR/data/submissions/submission-package" \
    --archive "$WORKDIR/data/submissions/submission-package.tar.gz"
fi

echo
echo "[$STEPS/$STEPS] Artifacts"
echo "- metadata: $WORKDIR/data/papers/metadata"
echo "- pdfs:     $WORKDIR/data/papers/pdfs"
echo "- parsed:   $WORKDIR/data/papers/parsed"
echo "- corpus:   $WORKDIR/data/kg/corpus-snapshot.json"
echo "- proposal: $WORKDIR/data/proposals/proposal-confirmed.json"
echo "- markdown: $WORKDIR/data/proposals/proposal-confirmed.md"
echo "- csv:      $WORKDIR/edges.csv, $WORKDIR/nodes.csv"
if [[ "$EXTENDED" -eq 1 ]]; then
  echo "- experiment: $WORKDIR/data/experiments/experiment-report.json"
  echo "- evaluation: $WORKDIR/data/experiments/evaluation-summary.json"
  echo "- manuscript: $WORKDIR/data/manuscripts/manuscript-draft.md"
  echo "- bundle:     $WORKDIR/data/submissions/submission-package"
  echo "- archive:    $WORKDIR/data/submissions/submission-package.tar.gz"
fi

if [[ "$MODE" == "hybrid" ]]; then
  echo
  echo "[optional] Network smoke tests (non-blocking)"
  set +e
  AUTOPAPERS_NETWORK_SMOKE=1 uv run pytest -q -m network \
    tests/test_papers_arxiv_provider.py::test_arxiv_search_returns_results \
    tests/test_openalex_provider.py::test_openalex_search_network_smoke
  RC=$?
  set -e
  if [[ $RC -ne 0 ]]; then
    echo "Network smoke failed or skipped (non-blocking)." >&2
    echo "Hint: check external network and provider endpoint reachability." >&2
  fi
fi
