from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import ServiceNotReady
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.registry import ProviderRegistry
from app.core.synthesizer import Synthesizer
from app.core.voice_catalog import VoiceCatalog


def require_ready(request: Request) -> None:
    """503 until the background warmup (model loading) has finished. Lets the server
    accept connections immediately at startup instead of blocking, so /healthz and
    /readyz stay responsive while models load."""
    if not getattr(request.app.state, "ready", False):
        raise ServiceNotReady("Service is starting up — models are still loading.")


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.registry
    return registry


def get_voice_catalog(request: Request) -> VoiceCatalog:
    catalog: VoiceCatalog = request.app.state.voice_catalog
    return catalog


def get_circuit_breakers(request: Request) -> CircuitBreakerRegistry:
    breakers: CircuitBreakerRegistry = request.app.state.circuit_breakers
    return breakers


def get_synthesizer(
    catalog: Annotated[VoiceCatalog, Depends(get_voice_catalog)],
    breakers: Annotated[CircuitBreakerRegistry, Depends(get_circuit_breakers)],
) -> Synthesizer:
    return Synthesizer(catalog, breakers)


VoiceCatalogDep = Annotated[VoiceCatalog, Depends(get_voice_catalog)]
SynthesizerDep = Annotated[Synthesizer, Depends(get_synthesizer)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]
