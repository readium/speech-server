from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from re import sub as re_sub
from typing import Any, ClassVar

import anyio

from app.api.errors import ProviderError
from app.core.concurrency import run_inference
from app.providers.base import TTSProvider
from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Voice

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

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}  # lang_key → TTSModel
        self._model_locks: dict[str, threading.Lock] = {}  # per-model lock; not thread-safe
        self._voice_states: dict[str, Any] = {}  # voiceURI → voice state
        self._voice_lang: dict[str, str] = {}  # voiceURI → lang_key
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
        self._voices = [
            Voice(**{**v, "boundary": self.supports_boundaries})
            for v in raw
            if v["language"].split("-")[0].lower() in enabled
        ]

        lang_voices: dict[str, list[Voice]] = {}
        for voice in self._voices:
            key = voice.language.split("-")[0].lower()
            lang_voices.setdefault(key, []).append(voice)
            self._voice_lang[voice.voiceURI] = key

        for lang_key, voices in lang_voices.items():
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
                len(voices),
            )
            for voice in voices:
                self._voice_states[voice.voiceURI] = model.get_state_for_audio_prompt(
                    voice.engineVoiceId
                )

        logger.info(
            "PocketTTS ready — %d voices across %d language models",
            len(self._voices),
            len(self._models),
        )
        return True

    async def _all_voices(self) -> Sequence[Voice]:
        return self._voices

    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        if params.voice_uri not in self._voice_states:
            raise ProviderError(f"Unknown PocketTTS voice: {params.voice_uri}")

        text = _strip_ssml(params.text) if params.ssml else params.text
        if not text:
            raise ProviderError("Text is empty after stripping SSML tags")

        if params.speed != 1.0 or params.pitch is not None:
            logger.debug(
                "PocketTTS ignores speed/pitch (not supported); speed=%.2f pitch=%s",
                params.speed,
                params.pitch,
            )

        lang_key = self._voice_lang[params.voice_uri]
        model = self._models[lang_key]
        lock = self._model_locks[lang_key]
        state = self._voice_states[params.voice_uri]
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
