from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from re import sub as re_sub
from typing import Any, ClassVar

import anyio

from app.api.errors import ProviderError, VoiceLanguageUnsupported
from app.config.settings import settings
from app.core.concurrency import run_inference
from app.domain.enums import Quality
from app.providers.base import TTSProvider
from app.providers.voice_loading import VoiceEntry, build_voice, plan_install
from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Controls, Voice

logger = logging.getLogger(__name__)

_VOICES_PATH = Path(__file__).parent.parent / "data" / "voices" / "pocket" / "voices.json"

# BCP-47 prefix → pocket-tts language identifier
_LANG_MODEL: dict[str, str] = {
    "en": "english",
    "fr": "french_24l",
    "it": "italian",
    "de": "german_24l",
    "es": "spanish_24l",
    "pt": "portuguese",
}


def _strip_ssml(text: str) -> str:
    return re_sub(r"<[^>]+>", "", text).strip()


class PocketTTSProvider(TTSProvider):
    id = "pocket"
    supported_languages: ClassVar[frozenset[str]] = frozenset(_LANG_MODEL.keys())
    default_quality: ClassVar[Quality] = Quality.VERY_HIGH
    default_controls: ClassVar[Controls] = Controls(
        pitch=False, speed=False, ssml=False, boundary=False
    )

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}  # lang_key → TTSModel
        self._model_locks: dict[str, threading.Lock] = {}  # per-model lock; not thread-safe
        self._voice_states: dict[tuple[str, str], Any] = {}  # (identifier, lang_key) → voice state
        self._voice_default_lang: dict[str, str] = {}  # identifier → default lang (request omits)
        self._voice_langs: dict[str, frozenset[str]] = {}  # identifier → all warmed lang_keys
        self._voices: list[Voice] = []
        self._ready = False

    async def load(self) -> None:
        self._ready = await anyio.to_thread.run_sync(self._load_sync)

    def _load_sync(self) -> bool:
        import torch
        from pocket_tts import TTSModel

        torch.set_num_threads(1)

        enabled = self.active_languages()
        if not enabled:
            logger.warning("No PocketTTS-supported languages in LANGUAGES config")
            return False

        raw = json.loads(_VOICES_PATH.read_text())
        entries = [VoiceEntry.model_validate(v) for v in raw]

        install_all = settings.voice_install_all
        add_map = settings.voice_language_add_map
        remove_map = settings.voice_language_remove_map
        known_keys = {e.originalName.lower() for e in entries}
        for unknown in (set(add_map) | set(remove_map)) - known_keys:
            logger.warning(
                "VOICE_LANGUAGES references unknown voice '%s' — check spelling "
                "against voices.json originalName",
                unknown,
            )

        lang_voices: dict[str, list[tuple[VoiceEntry, str]]] = {}
        self._voices = []
        for entry in entries:
            key = entry.originalName.lower()
            primary = entry.language.split("-")[0].lower()
            no_op_add = add_map.get(key, frozenset()) & {primary}
            if no_op_add:
                logger.warning(
                    "VOICE_LANGUAGES add for '%s' includes %s, its own primary "
                    "language — no effect, already installed",
                    key,
                    sorted(no_op_add),
                )
            plan = plan_install(
                entry,
                enabled,
                install_all,
                add_map.get(key, frozenset()),
                remove_map.get(key, frozenset()),
            )
            # A voice runs in any enabled language it has an embedding for, using ONLY
            # that language's base model — its primary model is NOT required (see
            # plan_install / pocket_tts get_state_for_audio_prompt). None = no enabled
            # language applies; skip.
            if plan is None:
                if key in add_map or key in remove_map:
                    logger.warning(
                        "VOICE_LANGUAGES override for '%s' resolves to no enabled "
                        "language — nothing to install for it",
                        key,
                    )
                continue
            default_lang, installed = plan
            other_langs = installed - frozenset({primary})
            voice = build_voice(
                entry, self.id, other_langs, self.default_quality, self.default_controls
            )
            self._voices.append(voice)
            self._voice_default_lang[voice.identifier] = default_lang
            self._voice_langs[voice.identifier] = installed
            for lang_key in installed:
                lang_voices.setdefault(lang_key, []).append((entry, lang_key))

        for lang_key, pairs in lang_voices.items():
            model_id = _LANG_MODEL[lang_key]
            logger.info("Loading PocketTTS model: %s ...", model_id)
            model: Any = TTSModel.load_model(language=model_id)
            model.eval()
            self._models[lang_key] = model
            self._model_locks[lang_key] = threading.Lock()
            logger.info(
                "Loaded %s (sample_rate=%d Hz); warming %d voice states...",
                model_id,
                model.sample_rate,
                len(pairs),
            )
            for entry, _ in pairs:
                identifier = entry.identifier
                # Warm each voice defensively — one voice that fails to load its
                # embedding (bad name, missing file, network) must not abort startup
                # for every other voice. The (voice, lang) simply stays uninstalled;
                # synthesize() then returns a clean "not installed" error for it.
                try:
                    self._voice_states[(identifier, lang_key)] = model.get_state_for_audio_prompt(
                        entry.originalName
                    )
                except Exception as exc:  # noqa: BLE001 — never let one voice crash load
                    logger.warning(
                        "Skipping voice '%s' for '%s' — failed to warm: %s",
                        entry.originalName,
                        lang_key,
                        exc,
                    )

        logger.info(
            "PocketTTS ready — %d voices across %d language models",
            len(self._voices),
            len(self._models),
        )
        return True

    async def _all_voices(self) -> Sequence[Voice]:
        return self._voices

    def _resolve_lang_key(self, voice_uri: str, requested_language: str | None) -> str | None:
        """The warmed language to synthesize in. A requested language the voice is
        NOT installed for returns None — we never silently fall back to a different
        language (that would speak the wrong language for a (voice, lang) that was
        never downloaded). An omitted language uses the voice's default installed one."""
        warmed = self._voice_langs.get(voice_uri, frozenset())
        if requested_language:
            requested = requested_language.split("-")[0].lower()
            return requested if requested in warmed else None
        return self._voice_default_lang[voice_uri]

    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        # Neutral "unsupported" responses throughout — never reveal install/config
        # state (whether a voice/language was downloaded), only that it isn't served.
        if params.voice_uri not in self._voice_langs:
            raise VoiceLanguageUnsupported(f"Voice '{params.voice_uri}' is not supported.")

        lang_key = self._resolve_lang_key(params.voice_uri, params.language)
        if lang_key is None:
            # Requested a language this voice isn't served in — never silently fall
            # back to a different language.
            raise VoiceLanguageUnsupported(
                f"Voice '{params.voice_uri}' is not supported for language '{params.language}'."
            )
        state_key = (params.voice_uri, lang_key)
        if state_key not in self._voice_states:
            # Safety net: language is in the voice's set but its embedding never warmed
            # (a load-time failure that was logged and skipped). Still unsupported here.
            raise VoiceLanguageUnsupported(
                f"Voice '{params.voice_uri}' is not supported for language '{lang_key}'."
            )

        text = _strip_ssml(params.text) if params.ssml else params.text
        if not text:
            raise ProviderError("Text is empty after stripping SSML tags")

        if params.speed != 1.0 or params.pitch is not None:
            logger.debug(
                "PocketTTS ignores speed/pitch (not supported); speed=%.2f pitch=%s",
                params.speed,
                params.pitch,
            )

        model = self._models[lang_key]
        lock = self._model_locks[lang_key]
        state = self._voice_states[state_key]
        sample_rate: int = model.sample_rate

        def _infer() -> bytes:
            import numpy as np
            import torch

            try:
                with lock, torch.no_grad():
                    # copy_state=True (default) preserves the cached voice state for reuse.
                    # lock serializes calls per language model — generate_audio is not thread-safe.
                    audio = model.generate_audio(state, text)
            except (ValueError, RuntimeError) as exc:
                raise ProviderError(f"PocketTTS generation failed: {exc}") from exc

            # generate_audio returns [samples] (1D) for mono; guard against [channels, samples] too
            pcm_tensor = audio[0] if audio.ndim == 2 else audio
            pcm_array = pcm_tensor.numpy()
            return bytes((pcm_array * 32767).clip(-32768, 32767).astype(np.int16).tobytes())

        pcm = await run_inference(_infer)
        return AudioResult(pcm=pcm, sample_rate=sample_rate)

    async def health(self) -> bool:
        return self._ready
