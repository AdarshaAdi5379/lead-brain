from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.discovery.models import DiscoveryQuery


@dataclass(frozen=True)
class BusinessCandidate:
    """
    Provider-agnostic business discovered from a lead source.

    Only fields known/available are populated; the rest stay None so the
    candidate list remains the single contract between a discovery provider
    and the pipeline (seed conversion).
    """

    business_name: str
    category: str = ""
    url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    opening_hours: Optional[str] = None
    osm_id: Optional[str] = None
    osm_type: Optional[str] = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    """Raised when a discovery provider cannot fulfil a search (e.g. bad
    location, upstream unavailability, invalid credentials)."""


class DiscoveryProvider(ABC):
    """Interface implemented by every lead-discovery source."""

    name: str = "base"

    @abstractmethod
    def search(
        self,
        query: DiscoveryQuery,
        *,
        radius: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[BusinessCandidate]:
        """Return business candidates for a single category+location query."""


class ProviderRegistry:
    """Statically registered discovery providers.

    Providers are registered lazily (on first ``get``) thanks to the
    convenience factory :func:`get_provider`, keeping the registry free of
    import cycles between provider modules.
    """

    def __init__(self) -> None:
        self._factories: dict[str, "PROVIDER_FACTORY"] = {}

    def register(self, name: str, factory: "PROVIDER_FACTORY") -> None:
        self._factories[name] = factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def get(self, name: str) -> DiscoveryProvider:
        name = (name or "").strip().lower()
        factory = self._factories.get(name)
        if factory is None:
            available = ", ".join(self.names())
            raise ProviderError(
                f"Unknown discovery provider '{name}'. Available providers: {available}"
            )
        return factory()


PROVIDER_FACTORY = Callable[[], DiscoveryProvider]

_registry = ProviderRegistry()


def _register(name: str, module_path: str, class_name: str) -> None:
    def _factory() -> DiscoveryProvider:
        import importlib

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()

    _registry.register(name, _factory)


def register_provider(name: str, factory: "PROVIDER_FACTORY") -> None:
    """Programmatic registration for tests/custom providers."""
    _registry.register(name, factory)


def get_provider(name: str) -> DiscoveryProvider:
    """Instantiate a provider by its registered name."""
    return _registry.get(name)


def available_providers() -> list[str]:
    return _registry.names()


def _register_builtins() -> None:
    if "osm" not in _registry.names():
        _register("osm", "src.discovery.osm", "OpenStreetMapProvider")
    if "google" not in _registry.names():
        _register("google", "src.discovery.google", "GooglePlacesProvider")


_register_builtins()