from __future__ import annotations

import base64
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from re import sub as re_sub
from typing import ClassVar

import httpx

from app.api.errors import (
    ProviderError,
    ProviderTimeout,
    RateLimited,
    VoiceLanguageUnsupported,
)
from app.config.settings import settings
from app.core.daily_limit import reserve
from app.domain.enums import AudioFormat, Quality
from app.drivers import ffmpeg as ffmpeg_driver
from app.providers.base import TTSProvider
from app.providers.voice_loading import VoiceEntry, build_voice, plan_install
from app.schemas.audio import AudioResult, SynthesisParams, TimingMark
from app.schemas.voice import Controls, Voice

logger = logging.getLogger(__name__)

_VOICES_PATH = Path(__file__).parent.parent / "data" / "voices" / "elevenlabs" / "voices.json"

_TIMEOUT_SECONDS = 30.0

# ElevenLabs API voice_id per voices.json originalName — mapped HERE (in code), keeping voices.json
# a readable catalog (name/originalName like "george", not opaque ids). Add an entry when adding a
# voice. A voice whose originalName isn't in this map falls back to using originalName as the id.
_VOICE_IDS: dict[str, str] = {
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "alice": "Xb7hH8MSUJpSbSDYk0k2",
    "brian": "nPczCjzI2devNBz1zQrb",
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "river": "SAz9YHcvj6GT2YYXdXww",
}

# ElevenLabs encodes server-side — request the requested format natively and skip our
# ffmpeg. Cost is per-character regardless of format (verified); only tier gates some
# variants (mp3_192=Creator+, pcm/wav_44100+=Pro+), so these are all free-tier-safe.
# Native mp3/opus at 44.1/48kHz also beats pcm_24000's 24kHz ceiling on non-Pro tiers.
_MP3_BITRATES = (32, 64, 96, 128)  # 192 needs Creator tier — excluded
_OPUS_BITRATES = (32, 64, 96, 128, 192)


def _nearest(bitrate: int | None, allowed: tuple[int, ...], default: int) -> int:
    """Largest allowed bitrate ≤ requested; default when unset/too low."""
    if bitrate is None:
        return default
    ok = [b for b in allowed if b <= bitrate]
    return max(ok) if ok else min(allowed)


def _output_format(fmt: AudioFormat, bitrate: int | None) -> tuple[str, str, int]:
    """(elevenlabs output_format, our content-type, sample_rate) for a requested format.
    All variants are free-tier-safe (wav_44100/pcm_44100 would need Pro, so wav uses 24k)."""
    if fmt == AudioFormat.MP3:
        return f"mp3_44100_{_nearest(bitrate, _MP3_BITRATES, 128)}", "audio/mpeg", 44100
    if fmt == AudioFormat.OPUS:
        return (
            f"opus_48000_{_nearest(bitrate, _OPUS_BITRATES, 128)}",
            ffmpeg_driver.content_type("opus"),
            48000,
        )
    return "wav_24000", "audio/wav", 24000  # AudioFormat.WAV


# Languages COMMON TO ALL ElevenLabs models (multilingual_v2 ∩ flash/turbo_v2.5 ∩ v3 = the 29
# multilingual_v2 languages), so behaviour is model-independent regardless of ELEVENLABS_MODEL_ID.
# All are free-tier usable — free tier only paywalls Voice-Library VOICES, not languages. This is
# the ceiling; a voice may narrow its set via otherLanguages in voices.json, and what's actually
# SERVED is this ∩ ELEVENLABS_LANGUAGES. Deliberately not the full per-model catalog (v3=70+).
# ponytail: model-independent flat set; if we ever need a model's extra languages (v2.5 hu/no/vi,
# v3's 40+ more), reintroduce a per-model models.json keyed by model_id.
_SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {
        "ar",
        "bg",
        "cs",
        "da",
        "de",
        "el",
        "en",
        "es",
        "fi",
        "fil",
        "fr",
        "hi",
        "hr",
        "id",
        "it",
        "ja",
        "ko",
        "ms",
        "nl",
        "pl",
        "pt",
        "ro",
        "ru",
        "sk",
        "sv",
        "ta",
        "tr",
        "uk",
        "zh",
    }
)


def _strip_ssml(text: str) -> str:
    return re_sub(r"<[^>]+>", "", text).strip()


def _alignment_to_marks(
    characters: list[str],
    starts: list[float],
    ends: list[float],  # noqa: ARG001 — kept for signature symmetry; word start is what boundary needs
) -> list[TimingMark]:
    """ElevenLabs alignment is per-character; the Web Speech boundary event is
    per-word. Walk the char arrays, split on whitespace, emit one mark per word.
    charIndex/charLength index into "".join(characters) == the text we SENT.
    # when params.ssml was stripped, offsets are into the stripped text,
    # not the raw request text — acceptable for boundary highlighting."""
    marks: list[TimingMark] = []
    i = 0
    n = len(characters)
    while i < n:
        if characters[i].isspace():
            i += 1
            continue
        start_idx = i
        word_start = starts[i]
        while i < n and not characters[i].isspace():
            i += 1
        marks.append(
            TimingMark(
                name="word",
                charIndex=start_idx,
                charLength=i - start_idx,
                elapsedTime=word_start,
            )
        )
    return marks


class ElevenLabsProvider(TTSProvider):
    id = "elevenlabs"
    default_quality: ClassVar[Quality] = Quality.HIGH
    # v2 has no pitch and only partial SSML; speed maps to voice_settings.speed,
    # boundary comes from the /with-timestamps alignment.
    default_controls: ClassVar[Controls] = Controls(
        pitch=False, speed=True, ssml=False, boundary=True
    )

    # active_languages() intersects this with ELEVENLABS_LANGUAGES.
    supported_languages: ClassVar[frozenset[str]] = _SUPPORTED_LANGUAGES

    def __init__(self) -> None:
        self._voices: list[Voice] = []
        self._voice_langs: dict[str, frozenset[str]] = {}  # identifier → installed lang keys
        self._voice_default_lang: dict[str, str] = {}  # identifier → default lang (request omits)
        self._voice_id: dict[str, str] = {}  # identifier → ElevenLabs voice_id (entry.originalName)

    def active_languages(self) -> frozenset[str]:
        """Languages are PROVIDER-SCOPED: intersect the supported set with this provider's own
        ELEVENLABS_LANGUAGES (elevenlabs.env), NOT the global LANGUAGES pocket uses."""
        configured = {lang.split("-")[0].lower() for lang in settings.elevenlabs_language_list}
        supported = {lang.split("-")[0].lower() for lang in self.supported_languages}
        return frozenset(supported & configured)

    async def load(self) -> None:
        # No network at startup: read the curated catalog and run the shared
        # voices.json → installed-Voice pipeline (same as pocket, minus model loading).
        enabled = self.active_languages()  # supported set ∩ ELEVENLABS_LANGUAGES
        if not enabled:
            logger.warning("No languages in ELEVENLABS_LANGUAGES — ElevenLabs serves no voices")
            return

        raw = json.loads(_VOICES_PATH.read_text())
        entries = [VoiceEntry.model_validate(v) for v in raw]

        add_map = settings.voice_language_add_map
        remove_map = settings.voice_language_remove_map

        model_langs = self.supported_languages
        for entry in entries:
            key = entry.originalName.lower()
            primary = entry.language.split("-")[0].lower()
            # Cross-language: ElevenLabs voices are multilingual, so a voice serves the whole
            # supported set (bounded by ELEVENLABS_LANGUAGES). A voice may narrow this by declaring
            # its own otherLanguages in voices.json (e.g. a language-locked cloned voice). We ALSO
            # curate native-sounding voices per language (primary set accordingly) so each language
            # has a natural voice, not only English voices cross-speaking it.
            if entry.otherLanguages:
                declared = {p.split("-")[0].lower() for p in entry.otherLanguages}
                entry.otherLanguages = sorted((declared & model_langs) - {primary})
            else:
                entry.otherLanguages = sorted(model_langs - {primary})
            plan = plan_install(
                entry,
                enabled,
                True,
                add_map.get(key, frozenset()),
                remove_map.get(key, frozenset()),
            )
            if plan is None:
                continue
            default_lang, installed = plan
            other_langs = installed - frozenset({primary})
            voice = build_voice(
                entry, self.id, other_langs, self.default_quality, self.default_controls
            )
            self._voices.append(voice)
            self._voice_default_lang[voice.identifier] = default_lang
            self._voice_langs[voice.identifier] = installed
            # ElevenLabs API voice_id from the internal map; fall back to originalName.
            self._voice_id[voice.identifier] = _VOICE_IDS.get(
                entry.originalName.lower(), entry.originalName
            )

        logger.info("ElevenLabs ready — %d voices", len(self._voices))

    async def _all_voices(self) -> Sequence[Voice]:
        return self._voices

    def _resolve_lang_key(self, voice_uri: str, requested_language: str | None) -> str | None:
        """Warmed language to synthesize in. A requested language the voice isn't
        served in returns None — never silently fall back to a different language."""
        installed = self._voice_langs.get(voice_uri, frozenset())
        if requested_language:
            requested = requested_language.split("-")[0].lower()
            return requested if requested in installed else None
        return self._voice_default_lang[voice_uri]

    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        # Neutral "unsupported" responses — never reveal config state, only that it
        # isn't served (mirrors pocket).
        if params.voice_uri not in self._voice_langs:
            raise VoiceLanguageUnsupported(f"Voice '{params.voice_uri}' is not supported.")

        lang_key = self._resolve_lang_key(params.voice_uri, params.language)
        if lang_key is None:
            raise VoiceLanguageUnsupported(
                f"Voice '{params.voice_uri}' is not supported for language '{params.language}'."
            )

        text = _strip_ssml(params.text) if params.ssml else params.text
        if not text:
            raise ProviderError("Text is empty after stripping SSML tags")

        # Daily budget: reserve the characters we're about to send. Set the limit per your model's
        # rate (see https://elevenlabs.io/pricing/api — flash/turbo bill half). Reserve BEFORE the
        # call so parallel requests can't overshoot; unlimited when limit=0.
        allowed, used = reserve(
            settings.elevenlabs_usage_file, len(text), settings.elevenlabs_daily_char_limit
        )
        if not allowed:
            raise RateLimited(
                f"Daily ElevenLabs limit reached "
                f"({used}/{settings.elevenlabs_daily_char_limit} characters today) — resets at "
                "00:00 UTC."
            )

        voice_id = self._voice_id[params.voice_uri]
        url = f"{settings.elevenlabs_base_url}/v1/text-to-speech/{voice_id}/with-timestamps"
        body = {
            "text": text,
            "model_id": settings.elevenlabs_model_id,
            "language_code": lang_key,
            "voice_settings": {"speed": params.speed},
        }
        headers = {"xi-api-key": settings.elevenlabs_api_key}
        el_format, content_type, sample_rate = _output_format(params.audio_format, params.bitrate)
        params_q = {"output_format": el_format}

        # async httpx directly — this is network I/O, NOT the CPU-bound work
        # run_inference()/the semaphore exist for. Per-request client; a shared pooled
        # client is the upgrade path if connection setup cost ever shows up in latency.
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=body, headers=headers, params=params_q)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"ElevenLabs request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"ElevenLabs request failed: {exc}") from exc

        if resp.status_code != 200:
            self._raise_for_status(resp, params.voice_uri, lang_key)

        data = resp.json()
        encoded = base64.b64decode(data["audio_base64"])  # already in el_format — no ffmpeg
        alignment = data.get("alignment") or {}
        marks = _alignment_to_marks(
            alignment.get("characters", []),
            alignment.get("character_start_times_seconds", []),
            alignment.get("character_end_times_seconds", []),
        )
        return AudioResult(
            sample_rate=sample_rate,
            boundaries=marks,
            encoded=encoded,
            content_type=content_type,
        )

    @staticmethod
    def _raise_for_status(resp: httpx.Response, voice_uri: str, lang_key: str) -> None:
        code = resp.status_code
        if code == 429:
            raise RateLimited("ElevenLabs rate limit exceeded")
        if code == 402:
            # Voice needs a paid plan — free tier can't use Voice Library voices via the API.
            raise ProviderError(
                f"ElevenLabs voice '{voice_uri}' requires a paid plan "
                "(free tier can't use Voice Library voices via the API)"
            )
        if code in (401, 403):
            raise ProviderError("ElevenLabs authentication failed — check ELEVENLABS_API_KEY")
        if code in (404, 422):
            # Bad voice_id or unsupported language — stay neutral like pocket.
            raise VoiceLanguageUnsupported(
                f"Voice '{voice_uri}' is not supported for language '{lang_key}'."
            )
        raise ProviderError(f"ElevenLabs returned {code}: {resp.text[:200]}")

    async def health(self) -> bool:
        return bool(self._voices and settings.elevenlabs_api_key)
