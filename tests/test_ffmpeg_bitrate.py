from app.drivers.ffmpeg import bitrate_args


def test_defaults_are_speech_sized():
    assert bitrate_args("opus", None) == ["-b:a", "32k"]
    assert bitrate_args("mp3", None) == ["-b:a", "64k"]


def test_request_bitrate_wins():
    assert bitrate_args("opus", 64) == ["-b:a", "64k"]


def test_wav_has_no_bitrate():
    assert bitrate_args("wav", None) == []
