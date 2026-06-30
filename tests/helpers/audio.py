"""Structural audio assertion helpers — never byte-exact."""

from __future__ import annotations

import struct

from app.schemas.audio import AudioResult


def assert_valid_pcm(result: AudioResult) -> None:
    """Non-empty PCM bytes; length is a whole number of 16-bit samples."""
    assert result.pcm is not None, "AudioResult.pcm is None"
    assert len(result.pcm) > 0, "PCM is empty"
    assert len(result.pcm) % 2 == 0, "PCM length is not a whole number of 16-bit samples"
    assert result.sample_rate > 0, "sample_rate must be positive"


def pcm_duration_seconds(result: AudioResult) -> float:
    """Convert PCM byte length to duration in seconds (16-bit mono assumed)."""
    assert result.pcm is not None
    samples = len(result.pcm) // 2  # 16-bit = 2 bytes per sample
    return samples / result.sample_rate


def assert_valid_wav(data: bytes) -> None:
    """RIFF/WAVE header present, non-zero data chunk."""
    assert len(data) >= 44, "WAV too short for header"
    assert data[:4] == b"RIFF", "Missing RIFF marker"
    assert data[8:12] == b"WAVE", "Missing WAVE marker"
    assert data[12:16] == b"fmt ", "Missing fmt  chunk"
    data_size = struct.unpack_from("<I", data, 40)[0]
    assert data_size > 0, "WAV data chunk is empty"
