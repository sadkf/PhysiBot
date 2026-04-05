"""LLM provider configurations and factory."""

from __future__ import annotations

from dataclasses import dataclass

from physi_core.config.settings import LLMConfig


@dataclass(frozen=True)
class ProviderDefaults:
    """Default SDK and base_url for a provider."""

    sdk: str  # "anthropic" or "openai"
    base_url: str


PROVIDER_REGISTRY: dict[str, ProviderDefaults] = {
    "minimax": ProviderDefaults(sdk="anthropic", base_url="https://api.minimaxi.com/anthropic"),
    "minimax_openai": ProviderDefaults(sdk="openai", base_url="https://api.minimax.io/v1"),
    "anthropic": ProviderDefaults(sdk="anthropic", base_url="https://api.anthropic.com"),
    "openai": ProviderDefaults(sdk="openai", base_url="https://api.openai.com/v1"),
}


def resolve_provider(config: LLMConfig) -> tuple[str, str]:
    """Resolve the SDK type and base_url for a given LLM config.

    Returns:
        (sdk_type, base_url) where sdk_type is 'anthropic' or 'openai'.
    """
    defaults = PROVIDER_REGISTRY.get(config.provider)
    if defaults is None:
        raise ValueError(
            f"Unknown provider '{config.provider}'. "
            f"Available: {list(PROVIDER_REGISTRY.keys())}"
        )
    base_url = config.base_url if config.base_url else defaults.base_url
    return defaults.sdk, base_url
