"""Frontend-friendly meeting processing entry point."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Callable

from .analyzer import analyze_transcript
from .diarization import diarize_segments
from .models import MeetingResult, TranscriptSegment
from .transcription import transcribe_audio


class MeetingProcessingError(RuntimeError):
    """Readable failure raised when a meeting cannot be processed."""


def process_meeting(
    audio_path: str | Path,
    *,
    meeting_date: str | None = None,
    language: str = "mixed",
    diarize: bool = True,
    speaker_count: int = 0,
    model: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> MeetingResult:
    """Process audio and return transcript, task list, and summary.

    The default interface is ``process_meeting(audio_path)``. Whisper, pyannote,
    and Ollama use local model files/services; no external AI API is called.
    """
    report = progress or (lambda _message: None)
    meeting_date = meeting_date or date.today().isoformat()
    try:
        transcript = transcribe_audio(audio_path, language=language, progress=report)
        warnings: list[str] = []
        if diarize:
            try:
                transcript = diarize_segments(
                    audio_path, transcript, speaker_count=speaker_count, progress=report
                )
            except Exception as exc:
                transcript = [replace(segment, speaker="SPEAKER_UNKNOWN") for segment in transcript]
                warnings.append(
                    "Диаризация недоступна; всем репликам присвоен SPEAKER_UNKNOWN. "
                    f"Причина: {exc}"
                )
        else:
            transcript = [replace(segment, speaker="SPEAKER_UNKNOWN") for segment in transcript]

        summary, tasks, analysis_warnings = analyze_transcript(
            transcript,
            meeting_date=meeting_date,
            model=model,
            progress=report,
        )
        warnings.extend(analysis_warnings)
        return MeetingResult(
            transcript=transcript,
            tasks=tasks,
            summary=summary,
            warnings=warnings,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise MeetingProcessingError(str(exc)) from exc
    except MeetingProcessingError:
        raise
    except Exception as exc:
        raise MeetingProcessingError(
            f"Meeting processing failed: {exc}. Check local models and setup instructions."
        ) from exc
