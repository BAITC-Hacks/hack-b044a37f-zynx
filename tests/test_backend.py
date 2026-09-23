"""Offline unit tests for the GUI-independent backend API."""

import unittest
from unittest.mock import patch

from src.analyzer import analyze_transcript
from src.models import MeetingTask, TranscriptSegment
from src.pipeline import MeetingProcessingError, process_meeting
from src.transcription import normalize_language


class BackendModelTests(unittest.TestCase):
    def test_transcript_schema_excludes_internal_word_timestamps(self):
        segment = TranscriptSegment(
            start=0, end=1.25, text=" Сәлем ", words=[{"start": 0, "end": 1, "word": "Сәлем"}]
        )
        self.assertEqual(
            segment.to_dict(),
            {"speaker": "SPEAKER_UNKNOWN", "start": 0.0, "end": 1.25, "text": "Сәлем"},
        )

    def test_invalid_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            TranscriptSegment(start=2, end=1, text="invalid")

    def test_task_serialization_uses_frontend_names(self):
        task = MeetingTask(task="Подготовить план", responsible="Айдана", deadline="2026-10-15")
        self.assertEqual(task.to_dict()["responsible"], "Айдана")
        self.assertNotIn("owner", task.to_dict())


class BackendAnalyzerTests(unittest.TestCase):
    def test_existing_local_agent_output_maps_to_backend_models(self):
        transcript = [TranscriptSegment(start=0, end=2, text="Подготовь план до 15 октября")]
        result = {
            "summary": "Обсудили план.",
            "warnings": ["Проверьте результат"],
            "tasks": [
                {
                    "task": "Подготовить план",
                    "owner": "Айдана",
                    "due_text": "15 октября",
                    "due_date": "2026-10-15",
                    "source_ids": [1],
                    "evidence": "Подготовь план до 15 октября",
                    "issues": [],
                    "status": "В работе",
                }
            ],
        }
        with patch("agent.analyze", return_value=result) as analyze:
            summary, tasks, warnings = analyze_transcript(transcript, meeting_date="2026-09-23")
        self.assertEqual(summary, "Обсудили план.")
        self.assertEqual(tasks[0].responsible, "Айдана")
        self.assertEqual(tasks[0].deadline, "2026-10-15")
        self.assertEqual(warnings, ["Проверьте результат"])
        self.assertEqual(analyze.call_args.args[0][0]["speaker"], "SPEAKER_UNKNOWN")

    def test_empty_transcript_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, "Transcript is empty"):
            analyze_transcript([])


class BackendPipelineTests(unittest.TestCase):
    @patch("src.pipeline.analyze_transcript", return_value=("Краткое саммари", [], []))
    @patch("src.pipeline.diarize_segments", side_effect=RuntimeError("weights unavailable"))
    @patch(
        "src.pipeline.transcribe_audio",
        return_value=[TranscriptSegment(start=0, end=1, text="Привет", speaker="SPEAKER_UNKNOWN")],
    )
    def test_diarization_failure_falls_back_without_losing_transcript(
        self, _transcribe, _diarize, _analyze
    ):
        result = process_meeting("meeting.wav", meeting_date="2026-09-23")
        self.assertEqual(result.transcript[0].speaker, "SPEAKER_UNKNOWN")
        self.assertEqual(result.summary, "Краткое саммари")
        self.assertIn("SPEAKER_UNKNOWN", result.warnings[0])

    @patch("src.pipeline.transcribe_audio", side_effect=FileNotFoundError("audio missing"))
    def test_transcription_failure_has_readable_processing_error(self, _transcribe):
        with self.assertRaisesRegex(MeetingProcessingError, "audio missing"):
            process_meeting("missing.wav")

    def test_language_aliases_support_russian_kazakh_and_mixed(self):
        self.assertEqual(normalize_language("русский"), "ru")
        self.assertEqual(normalize_language("қазақша"), "kk")
        self.assertIsNone(normalize_language("mixed"))


if __name__ == "__main__":
    unittest.main()
