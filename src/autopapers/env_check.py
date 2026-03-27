from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from autopapers import __version__ as autopapers_version
from autopapers.config import Paths, default_toml_path, get_paths
from autopapers.providers.polite_ua import polite_mailto


def build_doctor_payload(*, paths: Paths | None = None) -> dict[str, Any]:
    """
    Environment / optional-feature readiness (same JSON shape as ``autopapers doctor``), including
    whether the ``ollama`` executable is on PATH when using the Ollama LLM backend.

    ``paths`` should match the status snapshot when embedding in :func:`build_status`.
    """

    p = paths or get_paths()
    toml = default_toml_path()
    eng = {
        "tectonic": shutil.which("tectonic") is not None,
        "latexmk": shutil.which("latexmk") is not None,
        "pdflatex": shutil.which("pdflatex") is not None,
    }
    supported_llm = {"openai", "ollama", "stub"}
    llm_effective = (os.environ.get("AUTOPAPERS_LLM_BACKEND") or "openai").strip().lower()
    llm_ok = llm_effective in supported_llm
    return {
        "ok": True,
        "app_version": autopapers_version,
        "python": sys.version.split()[0],
        "paths": {"data_repo_root": str(p.repo_root.resolve())},
        "config": {
            "default_toml_path": str(toml),
            "default_toml_present": toml.is_file(),
            "autopapers_repo_root_env": bool(os.environ.get("AUTOPAPERS_REPO_ROOT", "").strip()),
        },
        "network_politeness": {
            "mailto_configured": polite_mailto() is not None,
        },
        "optional_features": {
            "aminer_api_key": bool((os.environ.get("AMINER_API_KEY") or "").strip()),
            "openai_api_key": bool((os.environ.get("OPENAI_API_KEY") or "").strip()),
            "llm_backend": llm_effective,
            "llm_supported_backends": sorted(supported_llm),
            "llm_backend_valid": llm_ok,
            "llm_backend_hint": (
                None
                if llm_ok
                else "Set AUTOPAPERS_LLM_BACKEND to openai|ollama|stub"
            ),
            "ollama_cli": shutil.which("ollama") is not None,
            "docker_cli": shutil.which("docker") is not None,
            "paper_fetcher_cli": shutil.which("paper-fetcher") is not None,
            "latex_engines": eng,
            "any_latex_engine": any(eng.values()),
        },
    }
