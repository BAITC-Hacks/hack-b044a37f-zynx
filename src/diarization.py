"""Optional local pyannote diarization and timestamp alignment."""

from __future__ import annotations

import os
from pathlib import Path

from .models import TranscriptSegment

# pyannote must not try to retrieve model files during meeting processing.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")


def _canonical_speakers(turns: list[dict]) -> list[TranscriptSegment]:
    names: dict[str, str] = {}
    result: list[TranscriptSegment] = []
    for turn in turns:
        label = str(turn.get("speaker") or "SPEAKER_UNKNOWN")
        if label not in names and label != "SPEAKER_UNKNOWN":
            names[label] = f"SPEAKER_{len(names):02d}"
        result.append(
            TranscriptSegment(
                start=turn["start"],
                end=turn["end"],
                text=turn["text"],
                speaker=names.get(label, "SPEAKER_UNKNOWN"),
            )
        )
    return result


def diarize_segments(
    audio_path: str | Path,
    segments: list[TranscriptSegment],
    speaker_count: int = 0,
    progress=None,
) -> list[TranscriptSegment]:
    """Assign speaker labels and align them to ASR words; all inference is local."""
    if not segments:
        return []
    if not 0 <= speaker_count <= 20:
        raise ValueError("speaker_count must be between 0 and 20")
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    try:
        import torch
        from faster_whisper import decode_audio
        from audio_engine import speaker_model
        from core import align_words
    except ImportError as exc:
        raise RuntimeError(
            "Local diarization dependencies are missing. Install requirements-diarization.txt."
        ) from exc

    if progress:
        progress("Локальная диаризация и привязка говорящих к словам")
    try:
        waveform = decode_audio(str(path), sampling_rate=16000)
        options = {"num_speakers": speaker_count} if speaker_count else {}
        output = speaker_model()(
            {"waveform": torch.from_numpy(waveform).unsqueeze(0), "sample_rate": 16000},
            **options,
        )
        annotation = output.exclusive_speaker_diarization
        diarization = []
        if hasattr(annotation, "itertracks"):
            for turn, _track, label in annotation.itertracks(yield_label=True):
                diarization.append(
                    {"start": float(turn.start), "end": float(turn.end), "speaker": str(label)}
                )
        else:
            for turn, label in annotation:
                diarization.append(
                    {"start": float(turn.start), "end": float(turn.end), "speaker": str(label)}
                )
        raw_segments = [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": segment.words,
            }
            for segment in segments
        ]
        aligned = align_words(raw_segments, diarization)
        return _canonical_speakers(aligned)
    except Exception as exc:
        raise RuntimeError(f"Local speaker diarization failed: {exc}") from exc
