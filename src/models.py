"""Typed data models shared by the backend and frontend integration layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any
from uuid import uuid4


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

    def to_turn_dict(self, ident: int) -> dict[str, Any]:
        """Serialize using the existing ZYNX web application's turn contract."""
        return {"id": ident, **self.to_dict()}


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
    deadline_text: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        due_text = self.deadline_text or self.deadline or "Не указан"
        due_date = self.deadline if self.deadline and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", self.deadline) else None
        # Keep the backend's readable field names while matching the existing
        # web application's owner/due_text/due_date/id task contract.
        result.update(
            {
                "owner": self.responsible,
                "due_text": due_text,
                "due_date": due_date,
            }
        )
        return result


@dataclass(slots=True)
class MeetingResult:
    """Complete result returned by :func:`process_meeting`."""

    transcript: list[TranscriptSegment] = field(default_factory=list)
    tasks: list[MeetingTask] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    def to_app_result(self) -> dict[str, Any]:
        """Return the existing web application's ``meeting.result`` shape."""
        return {
            "summary": self.summary,
            "decisions": list(self.decisions),
            "tasks": [task.to_dict() for task in self.tasks],
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": [segment.to_dict() for segment in self.transcript],
            "turns": [segment.to_turn_dict(index) for index, segment in enumerate(self.transcript, start=1)],
            **self.to_app_result(),
        }
