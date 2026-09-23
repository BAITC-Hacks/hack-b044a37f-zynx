"""Evidence-grounded task and summary extraction using local Ollama only."""

from __future__ import annotations

from datetime import date
import os
from typing import Callable

from .models import MeetingTask, TranscriptSegment


def analyze_transcript(
    transcript: list[TranscriptSegment],
    meeting_date: str | None = None,
    model: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, list[MeetingTask], list[str]]:
    """Return summary, tasks, and warnings from the existing local Ollama agent."""
    if not transcript:
        raise ValueError("Transcript is empty")
    meeting_date = meeting_date or date.today().isoformat()
    try:
        date.fromisoformat(meeting_date)
    except ValueError as exc:
        raise ValueError("meeting_date must be an ISO date such as 2026-09-23") from exc

    turns = [
        {
            "id": index,
            "speaker": segment.speaker,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        }
        for index, segment in enumerate(transcript, start=1)
    ]
    try:
        from agent import analyze

        result = analyze(
            turns,
            meeting_date,
            model or os.environ.get("ZYNX_LOCAL_MODEL", "qwen3:8b"),
            progress or (lambda _message: None),
        )
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Local meeting analysis failed: {exc}") from exc

    tasks = []
    for item in result.get("tasks", []):
        due_text = item.get("due_text")
        if due_text in (None, "", "Не указан", "Не указано", "белгісіз"):
            deadline = None
        else:
            deadline = item.get("due_date") or due_text
        tasks.append(
            MeetingTask(
                task=str(item.get("task", "")).strip(),
                responsible=str(item.get("owner") or "Не указан"),
                deadline=str(deadline) if deadline is not None else None,
                status=str(item.get("status") or "В работе"),
                evidence=str(item.get("evidence") or ""),
                source_ids=list(item.get("source_ids") or []),
                issues=list(item.get("issues") or []),
                reviewed=bool(item.get("reviewed", False)),
                deadline_text=str(due_text) if due_text is not None else None,
                id=str(item.get("id") or ""),
            )
        )
    warnings = [str(value) for value in result.get("warnings", [])]
    return str(result.get("summary", "")).strip(), tasks, warnings
