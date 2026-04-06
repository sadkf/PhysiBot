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
    # owner_qq: the QQ account that NapCat/OneBot logs in as (first item is used)
    owner_qq: list[str] = field(default_factory=list)
    # talk_qq: allowed private chat peer(s)
    talk_qq: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentConfig:
    """Agent behavior config."""

    segment_interval: int = 1800
    user_trigger_cooldown: int = 600
    confirm_dangerous: bool = True


@dataclass(frozen=True)
class PrivacyConfig:
    """Privacy filter config."""

    redact_sensitive: bool = False
    ignore_apps: list[str] = field(default_factory=list)
    sensitive_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MonitorConfig:
    """Built-in observability monitor settings."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class Settings:
    """Root configuration object."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    iot: HomeAssistantConfig = field(default_factory=HomeAssistantConfig)
    qq: QQConfig = field(default_factory=QQConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    data_dir: Path = Path("physi-data")


def _build_nested(cls: type, raw: dict[str, Any]) -> Any:
    """Recursively build a dataclass from a raw dict, ignoring unknown keys."""
    import dataclasses

    if not dataclasses.is_dataclass(cls):
        return raw

    field_types = {f.name: f.type for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}
    # Backward compatibility for old QQ config:
    # - qq.napcat.{ws_url, owner_qq} => qq.{ws_url, owner_qq}
    # - owner_qq: [a, b]  => owner_qq=[a], talk_qq=[b]
    # - owner_qq: "a"     => owner_qq=["a"]
    if cls.__name__ == "QQConfig":
        normalized = dict(raw)
        if isinstance(normalized.get("napcat"), dict):
            napcat = normalized.get("napcat", {})
            if "ws_url" not in normalized and "ws_url" in napcat:
                normalized["ws_url"] = napcat["ws_url"]
            if "owner_qq" not in normalized and "owner_qq" in napcat:
                normalized["owner_qq"] = napcat["owner_qq"]
            if "talk_qq" not in normalized and "talk_qq" in napcat:
                normalized["talk_qq"] = napcat["talk_qq"]
        if isinstance(normalized.get("owner_qq"), list):
            owners = [str(v) for v in normalized.get("owner_qq", []) if str(v).strip()]
            if owners:
                normalized["owner_qq"] = [owners[0]]
                if "talk_qq" not in normalized:
                    normalized["talk_qq"] = owners[1:] or [owners[0]]
        raw = normalized

    for key, val in raw.items():
        if key not in field_types:
            continue
        ft = field_types[key]
        # Resolve string annotations
        if isinstance(ft, str):
            ft = eval(ft)  # noqa: S307
        if dataclasses.is_dataclass(ft) and isinstance(val, dict):
            kwargs[key] = _build_nested(ft, val)
        elif ft == list[str] and isinstance(val, str):
            # Allow single string where a list is expected (e.g. owner_qq: "123")
            kwargs[key] = [val]
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
