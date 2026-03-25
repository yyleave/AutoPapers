from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_profile_from_json(path: Path) -> Any:
    """
    MVP placeholder for 'Profile Parsing'.

    Phase 1 will later support multi-turn extraction; for now we accept a JSON file.
    """

    return json.loads(path.read_text(encoding="utf-8"))

