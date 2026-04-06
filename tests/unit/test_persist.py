"""Tests for config persist helpers."""

from __future__ import annotations

from pathlib import Path

from physi_core.config.persist import (
    apply_config_patch,
    deep_merge,
    needs_initial_setup,
)


def test_deep_merge_nested() -> None:
    base = {"llm": {"model": "a", "api_key": "old"}, "agent": {"x": 1}}
    patch = {"llm": {"model": "b"}}
    out = deep_merge(base, patch)
    assert out["llm"]["model"] == "b"
    assert out["llm"]["api_key"] == "old"
    assert out["agent"]["x"] == 1


def test_apply_keep_api_key(tmp_path: Path) -> None:
    current = {"llm": {"provider": "openai", "api_key": "secret", "model": "gpt"}}
    patch = {"llm": {"provider": "openai", "api_key": "", "model": "gpt-4"}}
    merged = apply_config_patch(
        current, patch, keep_llm_api_key=True, previous_api_key="secret"
    )
    assert merged["llm"]["api_key"] == "secret"


def test_needs_initial_setup(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    assert needs_initial_setup(p) is True
    p.write_text("llm:\n  provider: openai\n  api_key: your-api-key-here\n", encoding="utf-8")
    assert needs_initial_setup(p) is True
    p.write_text("llm:\n  provider: openai\n  api_key: sk-real\n", encoding="utf-8")
    assert needs_initial_setup(p) is False
