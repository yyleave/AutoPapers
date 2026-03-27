from __future__ import annotations

import os
import shutil
import sys
from typing import Any

from autopapers import __version__ as autopapers_version
from autopapers.config import Paths, default_toml_path, get_paths
from autopapers.providers.polite_ua import polite_mailto


def build_llm_backend_diagnostics() -> dict[str, Any]:
    """Shared non-secret LLM backend diagnostics for config/doctor surfaces."""

    supported = ["openai", "ollama", "stub"]
    effective = (os.environ.get("AUTOPAPERS_LLM_BACKEND") or "openai").strip().lower()
    valid = effective in set(supported)
    return {
        "AUTOPAPERS_LLM_BACKEND": os.environ.get("AUTOPAPERS_LLM_BACKEND"),
        "effective_backend": effective,
        "supported_backends": supported,
        "backend_valid": valid,
        "backend_hint": (
            None if valid else "Set AUTOPAPERS_LLM_BACKEND to openai|ollama|stub"
        ),
        "AUTOPAPERS_OPENAI_MODEL": os.environ.get("AUTOPAPERS_OPENAI_MODEL"),
        "AUTOPAPERS_OLLAMA_MODEL": os.environ.get("AUTOPAPERS_OLLAMA_MODEL"),
    }


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
    llm = build_llm_backend_diagnostics()
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
            "llm_backend": llm["effective_backend"],
            "llm_supported_backends": llm["supported_backends"],
            "llm_backend_valid": llm["backend_valid"],
            "llm_backend_hint": llm["backend_hint"],
            "ollama_cli": shutil.which("ollama") is not None,
            "docker_cli": shutil.which("docker") is not None,
            "paper_fetcher_cli": shutil.which("paper-fetcher") is not None,
            "latex_engines": eng,
            "any_latex_engine": any(eng.values()),
        },
    }
