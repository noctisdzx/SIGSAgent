"""Runtime settings loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Paths (resolved relative to backend/ if relative)
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "../data")).resolve())
    runtime_dir: Path = field(default_factory=lambda: Path(os.getenv("RUNTIME_DIR", "../runtime")).resolve())

    # LLM
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_timeout: int = _env_int("LLM_TIMEOUT", 30)
    llm_max_retries: int = _env_int("LLM_MAX_RETRIES", 3)

    # Sim
    sim_tick_seconds: int = _env_int("SIM_TICK_SECONDS", 300)
    sim_real_tick_seconds: float = float(os.getenv("SIM_REAL_TICK_SECONDS", "1"))
    sim_autostart: bool = _env_bool("SIM_AUTOSTART", False)

    @property
    def db_path(self) -> Path:
        return self.runtime_dir / "memory.db"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
