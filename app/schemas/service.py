from pydantic import BaseModel

from app.domain.enums import AudioFormat, Quality


class OutputCapabilities(BaseModel):
    formats: list[AudioFormat]
    default: AudioFormat


class Limits(BaseModel):
    maxTextLength: int
    maxConcurrentSyntheses: int


class ProviderCapabilities(BaseModel):
    id: str
    installedLanguages: list[str]
    # Provider-level defaults — same values merged into each voice on GET /voices,
    # surfaced here too so a client can see what a provider supports at all without
    # inspecting a voice. controls includes disabled entries as `false` (unlike the
    # per-voice enabled-only shape on /voices) since this is "what's possible", not
    # "what's on".
    quality: Quality | None = None
    controls: dict[str, bool] = {}


class ServiceCapabilities(BaseModel):
    output: OutputCapabilities
    limits: Limits
    providers: list[ProviderCapabilities]
