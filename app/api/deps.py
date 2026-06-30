from typing import Annotated

from fastapi import Depends, Request

from app.core.registry import ProviderRegistry
from app.core.synthesizer import Synthesizer
from app.core.voice_catalog import VoiceCatalog


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry = request.app.state.registry
    return registry


def get_voice_catalog(request: Request) -> VoiceCatalog:
    catalog: VoiceCatalog = request.app.state.voice_catalog
    return catalog


def get_synthesizer(catalog: Annotated[VoiceCatalog, Depends(get_voice_catalog)]) -> Synthesizer:
    return Synthesizer(catalog)


VoiceCatalogDep = Annotated[VoiceCatalog, Depends(get_voice_catalog)]
SynthesizerDep = Annotated[Synthesizer, Depends(get_synthesizer)]
