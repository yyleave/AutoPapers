from __future__ import annotations

import os
from dataclasses import dataclass

import requests


def run_debate_stub(*, profile_summary: str, corpus_summary: str) -> dict[str, str]:
    """
    Placeholder debate: returns fixed-role strings for wiring Phase 2 orchestration.

    Replace with LLM-backed agents later.
    """
    return {
        "radical": (
            f"[HypothesisAgent] Propose a bold extension based on: {profile_summary[:200]}..."
        ),
        "conservative": (
            "[SanityAgent] Check feasibility: scope, compute, data availability; "
            "flag overstated claims."
        ),
        "killer": (
            "[KillerAgent] Reviewer attack: missing baselines, unclear contribution, "
            f"weak experimental design vs corpus: {corpus_summary[:200]}..."
        ),
    }


@dataclass(frozen=True)
class LLMConfig:
    backend: str
    model: str
    openai_base_url: str
    ollama_base_url: str
    timeout_seconds: float


def load_llm_config() -> LLMConfig:
    backend = os.environ.get("AUTOPAPERS_LLM_BACKEND", "openai").strip().lower()
    if backend not in {"openai", "ollama", "stub"}:
        raise ValueError(
            "Unsupported AUTOPAPERS_LLM_BACKEND. Use 'openai', 'ollama', or 'stub'. "
            f"Got: {backend!r}"
        )
    if backend == "openai":
        model = os.environ.get("AUTOPAPERS_OPENAI_MODEL", "gpt-4o-mini").strip()
    elif backend == "ollama":
        model = os.environ.get("AUTOPAPERS_OLLAMA_MODEL", "llama3.1:8b").strip()
    else:
        model = "stub"
    return LLMConfig(
        backend=backend,
        model=model or ("gpt-4o-mini" if backend == "openai" else "llama3.1:8b"),
        openai_base_url=os.environ.get("AUTOPAPERS_OPENAI_BASE_URL", "https://api.openai.com/v1")
        .strip()
        .rstrip("/"),
        ollama_base_url=os.environ.get("AUTOPAPERS_OLLAMA_BASE_URL", "http://localhost:11434")
        .strip()
        .rstrip("/"),
        timeout_seconds=float(os.environ.get("AUTOPAPERS_LLM_TIMEOUT", "45")),
    )


def _llm_setup_hint(backend: str) -> str:
    if backend == "openai":
        return (
            "LLM backend=openai but OPENAI_API_KEY is missing.\n"
            "Quick setup:\n"
            "  export AUTOPAPERS_LLM_BACKEND=openai\n"
            "  export OPENAI_API_KEY='sk-...'\n"
            "  # optional: export AUTOPAPERS_OPENAI_MODEL='gpt-4o-mini'"
        )
    return (
        "LLM backend=ollama but service/model is unavailable.\n"
        "Quick setup:\n"
        "  export AUTOPAPERS_LLM_BACKEND=ollama\n"
        "  ollama pull llama3.1:8b\n"
        "  ollama serve\n"
        "  # optional: export AUTOPAPERS_OLLAMA_MODEL='llama3.1:8b'"
    )


def _chat_once(
    *,
    cfg: LLMConfig,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    if cfg.backend == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(_llm_setup_hint("openai"))
        url = f"{cfg.openai_base_url}/chat/completions"
        payload = {
            "model": cfg.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=cfg.timeout_seconds)
        if resp.status_code >= 400:
            detail = resp.text[:300]
            hint = _llm_setup_hint("openai")
            raise ValueError(
                f"OpenAI request failed ({resp.status_code}): {detail}\n{hint}"
            )
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()

    url = f"{cfg.ollama_base_url}/api/chat"
    payload = {
        "model": cfg.model,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        resp = requests.post(url, json=payload, timeout=cfg.timeout_seconds)
    except requests.RequestException as exc:
        raise ValueError(f"Ollama request failed: {exc}\n{_llm_setup_hint('ollama')}") from exc
    if resp.status_code >= 400:
        detail = resp.text[:300]
        hint = _llm_setup_hint("ollama")
        raise ValueError(
            f"Ollama request failed ({resp.status_code}): {detail}\n{hint}"
        )
    data = resp.json()
    content = data.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"Ollama returned empty content.\n{_llm_setup_hint('ollama')}")
    return content.strip()


def run_debate(*, profile_summary: str, corpus_summary: str) -> dict[str, str]:
    cfg = load_llm_config()
    if cfg.backend == "stub":
        stub = run_debate_stub(profile_summary=profile_summary, corpus_summary=corpus_summary)
        stub["judge"] = "Stub judge synthesis: use conservative constraints and killer risks."
        stub["backend"] = "stub"
        stub["model"] = "stub"
        return stub
    shared_context = (
        "You are helping draft a research proposal.\n\n"
        f"Profile summary:\n{profile_summary[:1800]}\n\n"
        f"Corpus summary:\n{corpus_summary[:5000]}"
    )
    radical = _chat_once(
        cfg=cfg,
        system_prompt=(
            "You are HypothesisAgent (radical). Propose a bold but testable idea. "
            "Return concise markdown bullets."
        ),
        user_prompt=shared_context,
        temperature=0.8,
    )
    conservative = _chat_once(
        cfg=cfg,
        system_prompt=(
            "You are SanityAgent (conservative). Critique scope, feasibility, and evidence gaps. "
            "Return concise markdown bullets."
        ),
        user_prompt=shared_context + f"\n\nRadical draft:\n{radical[:3000]}",
        temperature=0.4,
    )
    killer = _chat_once(
        cfg=cfg,
        system_prompt=(
            "You are KillerAgent (reviewer). Identify likely rejection reasons, missing baselines, "
            "and failure modes. Return concise markdown bullets."
        ),
        user_prompt=(
            shared_context
            + f"\n\nRadical draft:\n{radical[:2600]}"
            + f"\n\nConservative critique:\n{conservative[:2600]}"
        ),
        temperature=0.5,
    )
    judge = _chat_once(
        cfg=cfg,
        system_prompt=(
            "You are JudgeAgent. Synthesize the debate into a practical proposal "
            "skeleton with sections: "
            "problem, hypothesis, contributions, baselines, risks, resources."
        ),
        user_prompt=(
            shared_context
            + f"\n\nRadical:\n{radical[:2400]}\n\nConservative:\n{conservative[:2400]}"
            + f"\n\nKiller:\n{killer[:2400]}"
        ),
        temperature=0.2,
    )
    return {
        "radical": radical,
        "conservative": conservative,
        "killer": killer,
        "judge": judge,
        "backend": cfg.backend,
        "model": cfg.model,
    }


def _extract_bullets(text: str, *, max_items: int, fallback: str) -> list[str]:
    lines = [ln.strip(" -*\t") for ln in text.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in lines:
        if len(ln) >= 6:
            out.append(ln[:220])
        if len(out) >= max_items:
            break
    if not out:
        return [fallback]
    return out


def merge_stub_to_proposal(
    *,
    title: str,
    debate: dict[str, str],
    status: str = "draft",
) -> dict[str, object]:
    cons = debate.get("conservative", "").strip()
    if len(cons) > 400:
        cons = f"{cons[:400]}…"
    radical = debate.get("radical", "")
    killer = debate.get("killer", "")
    judge = debate.get("judge", "")
    contributions = _extract_bullets(
        judge or radical,
        max_items=3,
        fallback="Initial contribution draft from debate synthesis.",
    )
    baselines = _extract_bullets(
        killer,
        max_items=3,
        fallback="A strong field baseline and one ablation baseline.",
    )
    risks = _extract_bullets(
        killer or cons,
        max_items=3,
        fallback="Compute / data access",
    )
    problem = (
        "Derived from profile keywords / problem statements.\n\n"
        f"Feasibility / scope (conservative): {cons}"
    )
    return {
        "schema_version": "0.1",
        "title": title,
        "problem": problem,
        "hypothesis": (radical or judge)[:700] or "Hypothesis draft unavailable.",
        "contributions": contributions,
        "baselines": baselines,
        "risks": risks,
        "resources": ["Corpus paths under data/papers/"],
        "debate_notes": debate,
        "status": status,
    }
