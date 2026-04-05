"""Unit tests for llm/adapter.py and llm/providers.py."""

from __future__ import annotations

import pytest

from physi_core.config.settings import LLMConfig
from physi_core.llm.providers import PROVIDER_REGISTRY, resolve_provider


class TestProviders:
    def test_minimax_resolves_to_anthropic_sdk(self) -> None:
        config = LLMConfig(provider="minimax")
        sdk, url = resolve_provider(config)
        assert sdk == "anthropic"
        assert "minimaxi.com" in url

    def test_anthropic_resolves_correctly(self) -> None:
        config = LLMConfig(provider="anthropic")
        sdk, url = resolve_provider(config)
        assert sdk == "anthropic"
        assert "anthropic.com" in url

    def test_openai_resolves_correctly(self) -> None:
        config = LLMConfig(provider="openai")
        sdk, url = resolve_provider(config)
        assert sdk == "openai"
        assert "openai.com" in url

    def test_custom_base_url_overrides_default(self) -> None:
        config = LLMConfig(provider="minimax", base_url="https://custom.api.com")
        _, url = resolve_provider(config)
        assert url == "https://custom.api.com"

    def test_unknown_provider_raises(self) -> None:
        config = LLMConfig(provider="unknown_provider")
        with pytest.raises(ValueError, match="Unknown provider"):
            resolve_provider(config)

    def test_all_registry_entries_have_required_fields(self) -> None:
        for name, defaults in PROVIDER_REGISTRY.items():
            assert defaults.sdk in ("anthropic", "openai"), f"{name} has invalid sdk"
            assert defaults.base_url.startswith("https://"), f"{name} has invalid base_url"
