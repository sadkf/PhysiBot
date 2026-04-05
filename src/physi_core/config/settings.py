"""Configuration management: load and validate YAML settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "minimax"
    model: str = "MiniMax-M2.7"
    api_key: str = ""
    base_url: str = ""


@dataclass(frozen=True)
class ScreenpipeConfig:
    """Screenpipe perception config."""

    enabled: bool = True
    api_url: str = "http://localhost:3030"


@dataclass(frozen=True)
class ActivityWatchConfig:
    """ActivityWatch perception config."""

    enabled: bool = True
    api_url: str = "http://localhost:5600"


@dataclass(frozen=True)
class ClipboardConfig:
    """Clipboard monitoring config."""

    enabled: bool = True
    poll_interval: int = 5


@dataclass(frozen=True)
class PerceptionConfig:
    """All perception sources."""

    screenpipe: ScreenpipeConfig = field(default_factory=ScreenpipeConfig)
    activitywatch: ActivityWatchConfig = field(default_factory=ActivityWatchConfig)
    clipboard: ClipboardConfig = field(default_factory=ClipboardConfig)


@dataclass(frozen=True)
class HomeAssistantConfig:
    """Home Assistant IoT config."""

    enabled: bool = False
    url: str = "http://homeassistant.local:8123"
    token: str = ""


@dataclass(frozen=True)
class QQConfig:
    """NapCatQQ config."""

    ws_url: str = "ws://localhost:3001"
    owner_qq: str = ""


@dataclass(frozen=True)
class AgentConfig:
    """Agent behavior config."""

    segment_interval: int = 1800
    user_trigger_cooldown: int = 600
    confirm_dangerous: bool = True


@dataclass(frozen=True)
class PrivacyConfig:
    """Privacy filter config."""

    ignore_apps: list[str] = field(default_factory=list)
    sensitive_keywords: list[str] = field(
        default_factory=lambda: ["password", "密码", "银行", "信用卡"]
    )


@dataclass(frozen=True)
class Settings:
    """Root configuration object."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    iot: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    qq: QQConfig = field(default_factory=QQConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    data_dir: Path = Path("physi-data")


def _build_nested(cls: type, raw: dict[str, Any]) -> Any:
    """Recursively build a dataclass from a raw dict, ignoring unknown keys."""
    import dataclasses

    if not dataclasses.is_dataclass(cls):
        return raw

    field_types = {f.name: f.type for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, val in raw.items():
        if key not in field_types:
            continue
        ft = field_types[key]
        # Resolve string annotations
        if isinstance(ft, str):
            ft = eval(ft)  # noqa: S307
        if dataclasses.is_dataclass(ft) and isinstance(val, dict):
            kwargs[key] = _build_nested(ft, val)
        else:
            kwargs[key] = val
    return cls(**kwargs)


def load_settings(config_path: Path | str) -> Settings:
    """Load settings from a YAML file. Missing fields use defaults."""
    path = Path(config_path)
    if not path.exists():
        return Settings()

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return _build_nested(Settings, raw)
