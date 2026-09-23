"""Local, GUI-independent backend API for ZYNX Minutes."""

from .models import MeetingResult, MeetingTask, TranscriptSegment
from .pipeline import process_meeting

__all__ = ["TranscriptSegment", "MeetingTask", "MeetingResult", "process_meeting"]
