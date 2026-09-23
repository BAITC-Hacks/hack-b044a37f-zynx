"""Typed data models shared by the backend and frontend integration layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TranscriptSegment:
    """A time-aligned utterance. ``words`` is internal diarization metadata."""

    start: float
    end: float
    text: str
    speaker: str = "SPEAKER_UNKNOWN"
    words: list[dict[str, Any]] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.start = float(self.start)
        self.end = float(self.end)
        self.text = str(self.text).strip()
        self.speaker = str(self.speaker or "SPEAKER_UNKNOWN")
        if self.start < 0 or self.end < self.start:
            raise ValueError("Transcript segment timestamps must satisfy 0 <= start <= end")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public transcript schema (without internal word data)."""
        return {
            "speaker": self.speaker,
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }


@dataclass(slots=True)
class MeetingTask:
    """One extracted assignment with provenance and review state."""

    task: str
    responsible: str = "Не указан"
    deadline: str | None = None
    status: str = "В работе"
    evidence: str = ""
    source_ids: list[int] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    reviewed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MeetingResult:
    """Complete result returned by :func:`process_meeting`."""

    transcript: list[TranscriptSegment] = field(default_factory=list)
    tasks: list[MeetingTask] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": [segment.to_dict() for segment in self.transcript],
            "tasks": [task.to_dict() for task in self.tasks],
            "summary": self.summary,
            "warnings": list(self.warnings),
        }
