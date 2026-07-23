"""Fast, no-network tests for the ElevenLabs provider's pure logic."""

from app.domain.enums import AudioFormat
from app.providers.elevenlabs import (
    _SUPPORTED_LANGUAGES,
    _alignment_to_marks,
    _nearest,
    _output_format,
)


def test_supported_languages_common_to_all_models() -> None:
    # The 29 languages common to every ElevenLabs model (= multilingual_v2 set) — model-independent,
    # all free-tier usable. Sanity: the six core + hi, plus the broader common set; no v2.5/v3-only
    # extras (hu, no, vi, th, cy, …) since those aren't in every model.
    assert len(_SUPPORTED_LANGUAGES) == 29
    assert {"en", "fr", "it", "de", "es", "pt", "hi", "ja", "zh", "ar"} <= _SUPPORTED_LANGUAGES
    assert not ({"hu", "no", "vi", "th", "cy"} & _SUPPORTED_LANGUAGES)


def test_output_format_mp3_maps_bitrate_and_stays_free_tier() -> None:
    fmt, ct, sr = _output_format(AudioFormat.MP3, 128)
    assert (fmt, ct, sr) == ("mp3_44100_128", "audio/mpeg", 44100)
    # 192 needs Creator tier — never emitted; caps at 128.
    assert _output_format(AudioFormat.MP3, 320)[0] == "mp3_44100_128"
    assert _output_format(AudioFormat.MP3, None)[0] == "mp3_44100_128"
    assert _output_format(AudioFormat.MP3, 50)[0] == "mp3_44100_32"


def test_output_format_opus_and_wav() -> None:
    assert _output_format(AudioFormat.OPUS, 192)[0] == "opus_48000_192"
    assert _output_format(AudioFormat.OPUS, 100)[0] == "opus_48000_96"
    fmt, ct, sr = _output_format(AudioFormat.WAV, None)
    assert (fmt, ct, sr) == ("wav_24000", "audio/wav", 24000)  # wav_44100 needs Pro


def test_nearest_picks_largest_le_requested() -> None:
    assert _nearest(100, (32, 64, 96, 128), 128) == 96
    assert _nearest(10, (32, 64, 96, 128), 128) == 32  # below all → smallest
    assert _nearest(None, (32, 64, 96, 128), 128) == 128


def test_alignment_to_marks_splits_words() -> None:
    # "Hi bye" — chars H,i,space,b,y,e with ascending start times.
    chars = ["H", "i", " ", "b", "y", "e"]
    starts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    marks = _alignment_to_marks(chars, starts, ends)

    assert len(marks) == 2
    hi, bye = marks
    assert (hi.charIndex, hi.charLength, hi.elapsedTime) == (0, 2, 0.0)
    assert (bye.charIndex, bye.charLength, bye.elapsedTime) == (3, 3, 0.3)
    # charIndex/charLength must index into "".join(chars)
    assert "".join(chars)[hi.charIndex : hi.charIndex + hi.charLength] == "Hi"
    assert "".join(chars)[bye.charIndex : bye.charIndex + bye.charLength] == "bye"
    assert all(m.name == "word" for m in marks)


def test_alignment_to_marks_handles_leading_and_multiple_spaces() -> None:
    chars = [" ", "a", " ", " ", "b"]
    starts = [0.0, 0.1, 0.2, 0.3, 0.4]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5]

    marks = _alignment_to_marks(chars, starts, ends)

    assert [(m.charIndex, m.charLength) for m in marks] == [(1, 1), (4, 1)]


def test_alignment_to_marks_empty() -> None:
    assert _alignment_to_marks([], [], []) == []
