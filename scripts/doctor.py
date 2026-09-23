"""Print readiness without exposing tokens or recording contents."""
from pathlib import Path
import importlib.util
import json
import sys
import urllib.request
base=Path(__file__).resolve().parents[1]
print('Python:',sys.version.split()[0])
for name in ['docx','reportlab','faster_whisper','torch']:
    print(name+':','installed' if importlib.util.find_spec(name) else 'MISSING')
for name in ['whisper-small','diarization']:
    print('Model '+name+':','present' if (base/'models'/name).is_dir() else 'MISSING')
try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:11434/api/tags',timeout=3) as r: data=json.load(r)
    print('Ollama models:',', '.join(x['name'] for x in data.get('models',[])) or 'none')
except Exception:
    print('Ollama: NOT RUNNING')
print('Start UI: python app.py → http://127.0.0.1:8765')
