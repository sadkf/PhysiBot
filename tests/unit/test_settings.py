"""Unit tests for config/settings.py."""

from __future__ import annotations

from pathlib import Path

from physi_core.config.settings import (
    LLMConfig,
    Settings,
    load_settings,
)


class TestLoadSettings:
    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        settings = load_settings(tmp_path / "nonexistent.yaml")
        assert isinstance(settings, Settings)
        assert settings.llm.provider == "minimax"
        assert settings.llm.model == "MiniMax-M2.7"

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("", encoding="utf-8")
        settings = load_settings(cfg)
        assert settings.llm.provider == "minimax"

    def test_partial_config_fills_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "llm:\n  provider: anthropic\n  api_key: sk-test\n",
            encoding="utf-8",
        )
        settings = load_settings(cfg)
        assert settings.llm.provider == "anthropic"
        assert settings.llm.api_key == "sk-test"
        assert settings.llm.model == "MiniMax-M2.7"  # default kept

    def test_full_config_loads_correctly(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            """
llm:
  provider: openai
  model: gpt-4o
  api_key: sk-xxx
qq:
  owner_qq: "123456"
agent:
  segment_interval: 900
privacy:
  ignore_apps:
    - KeePass
  sensitive_keywords:
    - secret
""",
            encoding="utf-8",
        )
        settings = load_settings(cfg)
        assert settings.llm.provider == "openai"
        assert settings.llm.model == "gpt-4o"
        assert settings.qq.owner_qq == "123456"
        assert settings.agent.segment_interval == 900
        assert "KeePass" in settings.privacy.ignore_apps
        assert "secret" in settings.privacy.sensitive_keywords

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("unknown_key: value\nllm:\n  provider: minimax\n", encoding="utf-8")
        settings = load_settings(cfg)
        assert settings.llm.provider == "minimax"

    def test_nested_perception_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "perception:\n  screenpipe:\n    enabled: false\n    api_url: http://custom:9999\n",
            encoding="utf-8",
        )
        settings = load_settings(cfg)
        assert settings.perception.screenpipe.enabled is False
        assert settings.perception.screenpipe.api_url == "http://custom:9999"
        assert settings.perception.activitywatch.enabled is True  # default


class TestLLMConfig:
    def test_frozen(self) -> None:
        cfg = LLMConfig()
        try:
            cfg.provider = "other"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass
