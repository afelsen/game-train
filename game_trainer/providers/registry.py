from __future__ import annotations

from .base import StrategyProvider, StrategyRequest, StrategyResponse


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, StrategyProvider] = {}

    def register(self, provider: StrategyProvider) -> None:
        if provider.provider_id in self._providers:
            raise ValueError(f"duplicate provider: {provider.provider_id}")
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> StrategyProvider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise KeyError(f"unknown provider: {provider_id}") from error

    def strategy(self, provider_id: str, request: StrategyRequest) -> StrategyResponse:
        provider = self.get(provider_id)
        supported, reason = provider.capabilities.supports(request)
        if not supported:
            return StrategyResponse.unsupported(request, provider, reason or "unsupported")
        return provider.strategy(request)

    def list(self, include_experimental: bool = False) -> tuple[StrategyProvider, ...]:
        providers = self._providers.values()
        if not include_experimental:
            providers = (provider for provider in providers if not provider.capabilities.experimental)
        return tuple(sorted(providers, key=lambda provider: provider.provider_id))

