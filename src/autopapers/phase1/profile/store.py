from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autopapers.config import get_paths


def save_profile(*, profile: Any, profiles_dir: Path | None = None) -> Path:
    paths = get_paths()
    out_dir = profiles_dir or paths.profiles_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"profile-{ts}.json"
    out_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path

