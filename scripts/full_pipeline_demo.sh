#!/usr/bin/env bash
set -euo pipefail

MODE="offline"
WORKDIR=""
TITLE="Full Pipeline Demo Topic"

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
    --title)
      TITLE="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/full_pipeline_demo.sh [--mode offline|hybrid] [--workdir /tmp/path] [--title "topic"]

Runs full AutoPapers orchestration demo:
  publish -> release -> release-verify -> phase5 verify -> flow -> status

Modes:
  offline  Fully local pipeline with local_pdf provider (default)
  hybrid   Offline pipeline + optional provider smoke tests (non-blocking)
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
cd "$REPO_ROOT"

if [[ -z "$WORKDIR" ]]; then
  WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/autopapers-full-XXXXXX")"
fi
mkdir -p "$WORKDIR"

echo "== AutoPapers Full Pipeline demo =="
echo "mode: $MODE"
echo "repo: $REPO_ROOT"
echo "workdir: $WORKDIR"

export AUTOPAPERS_REPO_ROOT="$WORKDIR"
export AUTOPAPERS_PROVIDER="local_pdf"
export AUTOPAPERS_LLM_BACKEND="${AUTOPAPERS_LLM_BACKEND:-stub}"

PDF_DIR="$WORKDIR/demo_pdfs"
PROFILE_JSON="$WORKDIR/user_profile.json"
export PDF_DIR PROFILE_JSON
mkdir -p "$PDF_DIR"

echo
echo "[1/9] Workspace config (configs/default.toml) + tiny local PDF fixture"
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
echo "[2/9] Init profile and patch local provider keyword"
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
echo "[3/9] Publish (run-all --full-flow --archive)"
uv run autopapers publish --profile "$PROFILE_JSON" --title "$TITLE"

echo
echo "[4/9] Release (publish + verify + checksums)"
uv run autopapers release --profile "$PROFILE_JSON" --title "$TITLE"

echo
echo "[5/9] Release re-verify"
uv run autopapers release-verify --release-report "$WORKDIR/data/releases/release-report.json"

echo
echo "[6/9] Phase5 verify (bundle vs archive, manifest parity)"
uv run autopapers phase5 verify \
  --bundle-dir "$WORKDIR/data/submissions/submission-package" \
  --archive "$WORKDIR/data/submissions/submission-package.tar.gz"

echo
echo "[7/9] Flow guidance"
uv run autopapers flow

echo
echo "[8/9] Status snapshot"
uv run autopapers status

echo
echo "[9/9] Core artifacts"
echo "- bundle:         $WORKDIR/data/submissions/submission-package"
echo "- archive:        $WORKDIR/data/submissions/submission-package.tar.gz"
echo "- release report: $WORKDIR/data/releases/release-report.json"
echo "- verify report:  $WORKDIR/data/releases/release-verify-report.json"

if [[ "$MODE" == "hybrid" ]]; then
  echo
  echo "[optional] Provider smoke tests (non-blocking)"
  set +e
  scripts/run_all_providers_smoke.sh
  RC=$?
  set -e
  if [[ $RC -ne 0 ]]; then
    echo "Provider smoke had failures/skips (non-blocking)." >&2
    echo "Hint: check external network and upstream API status." >&2
  fi
fi
