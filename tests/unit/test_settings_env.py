"""Tests for LLM API key from environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from physi_core.config.settings import load_settings


def test_load_settings_api_key_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PHYSIBOT_LLM_API_KEY", raising=False)
    monkeypatch.setenv("PHYSIBOT_LLM_API_KEY", "sk-from-env")
    p = tmp_path / "c.yaml"
    p.write_text(
        'llm:\n  provider: "minimax"\n  model: "m"\n  api_key: ""\n',
        encoding="utf-8",
    )
    s = load_settings(p)
    assert s.llm.api_key == "sk-from-env"
