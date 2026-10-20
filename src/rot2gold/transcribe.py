"""Speech-to-text with faster-whisper on the CPU (int8), language detected automatically."""

import wave
from functools import cache

import numpy as np
from faster_whisper import WhisperModel


def load_wav(path: str) -> np.ndarray:
    """Read the 16 kHz mono 16-bit wav written by fetch.

    We decode it ourselves: faster-whisper's own decoder calls PyAV with an argument
    that PyAV 19 no longer accepts.
    """
    with wave.open(path) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16 kHz mono 16-bit wav")
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


@cache
def model(name: str, compute_type: str = "int8") -> WhisperModel:
    return WhisperModel(name, device="cpu", compute_type=compute_type)


def transcribe(audio: str, name: str, compute_type: str = "int8") -> tuple[list[dict], str, float]:
    """Return (segments, language, language probability). Music-only audio gives no segments."""
    segs, info = model(name, compute_type).transcribe(load_wav(audio), beam_size=5, vad_filter=True)
    out = []
    for s in segs:
        text = s.text.strip()
        # Whisper's usual hallucination guard: likely silence and low confidence.
        if not text or (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0):
            continue
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
    return out, info.language, round(info.language_probability, 3)
