from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    base_url: str
    model: str
    max_turns: int
    workspace: Path
    context_tokens: int
    sessions_dir: Path


_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
}


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    preset = _PROVIDER_PRESETS.get(provider, {})

    api_key = (
        os.getenv(preset.get("api_key_env", ""), "")
        or os.getenv("LLM_API_KEY", "")
    ).strip()
    base_url = (
        os.getenv(f"{provider.upper()}_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or preset.get("base_url", "")
    ).strip()
    model = (
        os.getenv(f"{provider.upper()}_MODEL")
        or os.getenv("LLM_MODEL")
        or preset.get("model", "")
    ).strip()

    max_turns_raw = os.getenv("CODEAGENT_MAX_TURNS", "24").strip()
    try:
        max_turns = max(1, int(max_turns_raw))
    except ValueError:
        max_turns = 24

    workspace_raw = os.getenv("CODEAGENT_WORKSPACE", "").strip()
    workspace = (
        Path(workspace_raw).resolve()
        if workspace_raw
        else (_PROJECT_ROOT / "workspace").resolve()
    )
    workspace.mkdir(parents=True, exist_ok=True)

    context_raw = os.getenv("CODEAGENT_CONTEXT_TOKENS", "1000000").strip()
    try:
        context_tokens = max(1000, int(context_raw))
    except ValueError:
        context_tokens = 1_000_000

    sessions_raw = os.getenv("CODEAGENT_SESSIONS_DIR", "").strip()
    sessions_dir = (
        Path(sessions_raw).resolve()
        if sessions_raw
        else (_PROJECT_ROOT / "sessions").resolve()
    )
    sessions_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_turns=max_turns,
        workspace=workspace,
        context_tokens=context_tokens,
        sessions_dir=sessions_dir,
    )
