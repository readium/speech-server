import asyncio
import shutil

from app.api.errors import ProviderError

# (ffmpeg_args, content-type)
_FORMATS: dict[str, tuple[list[str], str]] = {
    "mp3": (["-f", "mp3"], "audio/mpeg"),
    "opus": (["-f", "ogg", "-c:a", "libopus"], "audio/ogg"),
    "wav": ([], "audio/wav"),  # wav bypasses ffmpeg; entry here makes content_type() safe
}


def is_available(ffmpeg_bin: str = "ffmpeg") -> bool:
    return shutil.which(ffmpeg_bin) is not None


def content_type(format: str) -> str:
    return _FORMATS[format][1]


async def encode(
    pcm: bytes,
    sample_rate: int,
    format: str,
    ffmpeg_bin: str = "ffmpeg",
    bitrate: int | None = None,
) -> bytes:
    fmt_args, _ = _FORMATS[format]
    bitrate_args = ["-b:a", f"{bitrate}k"] if bitrate else []

    cmd = [
        ffmpeg_bin,
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-i",
        "pipe:0",
        *fmt_args,
        *bitrate_args,
        "-loglevel",
        "error",
        "pipe:1",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ProviderError("ffmpeg launch failed", detail=str(exc)) from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(input=pcm), timeout=30)
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise ProviderError("ffmpeg encoding timed out") from exc

    if proc.returncode != 0:
        raise ProviderError(
            "ffmpeg encoding failed",
            detail=stderr.decode(errors="replace")[:300],
        )

    return stdout
