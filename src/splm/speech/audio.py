"""Audio in and out, with no audio library dependency.

Input: browsers record WebM/Opus or Ogg, so anything that is not plain PCM WAV is
decoded by the ``ffmpeg`` binary to 16 kHz mono float32. WAV is read with the
standard library. Output is 16-bit PCM WAV written with the standard library.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import wave

import numpy as np


class AudioError(ValueError):
    """The audio could not be decoded, or is outside the accepted limits."""


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Linear-interpolation resampling. Adequate for speech recognition input."""
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32)
    duration = samples.size / source_rate
    target_length = max(1, int(round(duration * target_rate)))
    source_times = np.arange(samples.size) / source_rate
    target_times = np.arange(target_length) / target_rate
    return np.interp(target_times, source_times, samples).astype(np.float32)


def read_wav(data: bytes, sample_rate: int = 16000) -> np.ndarray:
    """PCM WAV bytes -> mono float32 in [-1, 1] at ``sample_rate``."""
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioError(f"not a PCM WAV file: {exc}") from exc

    dtypes = {1: np.uint8, 2: np.int16, 4: np.int32}
    if width not in dtypes:
        raise AudioError(f"unsupported WAV sample width: {width} bytes")
    samples = np.frombuffer(frames, dtype=dtypes[width]).astype(np.float32)
    if width == 1:
        samples = (samples - 128.0) / 128.0
    else:
        samples /= float(2 ** (8 * width - 1))
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return _resample(samples, rate, sample_rate)


def decode_with_ffmpeg(data: bytes, sample_rate: int = 16000) -> np.ndarray:
    """Any container ffmpeg understands -> mono float32 at ``sample_rate``."""
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise AudioError(
            "ffmpeg is required to decode compressed audio (WebM/Ogg/MP3); "
            "install it (apt install ffmpeg) or send WAV"
        )
    process = subprocess.run(
        [binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "pipe:1"],
        input=data,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", "replace").strip().splitlines()
        raise AudioError(f"ffmpeg could not decode the audio: {message[-1] if message else 'unknown error'}")
    return np.frombuffer(process.stdout, dtype=np.float32).copy()


def decode_audio(data: bytes, sample_rate: int = 16000, max_seconds: float | None = None) -> np.ndarray:
    """Decode uploaded audio bytes, WAV natively and everything else via ffmpeg."""
    if not data:
        raise AudioError("empty audio")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            samples = read_wav(data, sample_rate)
        except AudioError:
            samples = decode_with_ffmpeg(data, sample_rate)  # e.g. float or ADPCM WAV
    else:
        samples = decode_with_ffmpeg(data, sample_rate)
    if samples.size == 0:
        raise AudioError("the audio decoded to zero samples")
    if max_seconds is not None and samples.size / sample_rate > max_seconds:
        raise AudioError(
            f"audio is {samples.size / sample_rate:.1f} s; the limit is {max_seconds:.0f} s "
            "(speech.asr.max_audio_seconds)"
        )
    return samples


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Float samples in [-1, 1] -> 16-bit PCM mono WAV bytes."""
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()
