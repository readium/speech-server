from pydantic import BaseModel

from app.domain.enums import AudioFormat


class OutputCapabilities(BaseModel):
    formats: list[AudioFormat]
    default: AudioFormat


class Limits(BaseModel):
    maxTextLength: int
    maxConcurrentSyntheses: int


class ProviderCapabilities(BaseModel):
    id: str
    installedLanguages: list[str]
    # Model-level quality/controls are NOT repeated here — they're merged into each
    # voice on GET /voices and documented per provider under docs/providers/.


class ServiceCapabilities(BaseModel):
    output: OutputCapabilities
    limits: Limits
    providers: list[ProviderCapabilities]
