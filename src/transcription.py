"""Local speech-to-text adapter using the repository's faster-whisper setup."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .models import TranscriptSegment

Progress = Callable[[str], None]


def normalize_language(language: str | None) -> str | None:
    """Map common UI labels to faster-whisper language codes; None means mixed/auto."""
    value = (language or "mixed").strip().lower()
    if value in {"ru", "russian", "русский", "русский язык"}:
        return "ru"
    if value in {"kk", "kz", "kazakh", "қазақша", "казахский"}:
        return "kk"
    return None


def transcribe_audio(
    audio_path: str | Path,
    language: str = "mixed",
    progress: Progress | None = None,
) -> list[TranscriptSegment]:
    """Transcribe an audio file locally and preserve word timestamps for diarization.

    Model weights must already exist locally; processing never calls a cloud API.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    try:
        from faster_whisper import decode_audio
        from audio_engine import whisper_model
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install requirements-audio.txt first."
        ) from exc

    if progress:
        progress("Локальное распознавание речи")
    waveform = decode_audio(str(path), sampling_rate=16000)
    if len(waveform) == 0:
        raise ValueError("The audio file contains no decodable audio")
    if len(waveform) > 16000 * 600:
        raise ValueError("For this MVP, audio must be 10 minutes or shorter")

    selected_language = normalize_language(language)
    try:
        segments, _info = whisper_model().transcribe(
            waveform,
            language=selected_language,
            multilingual=selected_language is None,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,
        )
        result: list[TranscriptSegment] = []
        for item in segments:
            text = str(item.text).strip()
            if not text:
                continue
            words = [
                {"start": float(word.start), "end": float(word.end), "word": word.word}
                for word in (item.words or [])
            ]
            result.append(
                TranscriptSegment(
                    start=float(item.start),
                    end=float(item.end),
                    text=text,
                    words=words or None,
                )
            )
    except Exception as exc:
        if isinstance(exc, (ValueError, RuntimeError)):
            raise
        raise RuntimeError(f"Local speech recognition failed: {exc}") from exc

    if not result:
        raise ValueError("No speech was detected in the audio")
    return result
