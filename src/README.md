# Backend API

The package in `src/` is independent of the web UI. A caller can process a local audio file with:

```python
from src import process_meeting

result = process_meeting("meeting.wav")
print(result.to_dict())
```

`MeetingResult` contains `transcript`, `tasks`, `summary`, and warnings. Transcript objects serialize as `{speaker, start, end, text}`. Task objects contain the action, responsible person, deadline, status, and source evidence.

## Local setup

Use Python 3.11 or 3.12, then install the full backend dependencies:

```powershell
python -m pip install -r requirements-backend.txt
python scripts/download_models.py --whisper small --diarization
```

For diarization, first accept the model terms for `pyannote/speaker-diarization-community-1` and provide a Hugging Face read token to the download script. Model files are stored under `models/` and excluded from Git.

Task extraction and summarization use the existing local Ollama integration. Install/start Ollama, download a local model such as `qwen3:8b`, and set `ZYNX_LOCAL_MODEL` if you want another local model. No OpenAI, Google, Azure, or other hosted AI API is used. Internet access is needed only to install packages and download model files, not while processing a meeting.

If local diarization cannot load, processing continues with `SPEAKER_UNKNOWN` labels and a warning. Speech recognition or local analysis errors are raised as `MeetingProcessingError` with setup guidance.

Run the offline backend unit tests from the repository root:

```powershell
python -m unittest tests.test_backend -v
```
