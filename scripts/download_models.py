"""Preparation only; internet required. Meeting data never enters this script."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import json

p=argparse.ArgumentParser(description='Download local model weights before the demo')
p.add_argument('--whisper',choices=['tiny','base','small','medium','large-v3'])
p.add_argument('--diarization',action='store_true')
args=p.parse_args()
if not args.whisper and not args.diarization: p.error('Choose --whisper small and/or --diarization')
os.environ.pop('HF_HUB_OFFLINE',None)
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
from huggingface_hub import snapshot_download
base=Path(__file__).resolve().parents[1]/'models'; base.mkdir(exist_ok=True)
records=[]
if args.whisper:
    repo='Systran/faster-whisper-'+args.whisper
    target=base/('whisper-'+args.whisper)
    snapshot_download(repo_id=repo,local_dir=str(target))
    records.append({'repo':repo,'path':str(target)})
    print('Whisper downloaded:',target)
if args.diarization:
    print('First accept the model terms at https://huggingface.co/pyannote/speaker-diarization-community-1')
    token=os.environ.get('HF_TOKEN') or getpass('Hugging Face read token (hidden): ')
    repo='pyannote/speaker-diarization-community-1'
    target=base/'diarization'
    snapshot_download(repo_id=repo,token=token,local_dir=str(target))
    records.append({'repo':repo,'path':str(target)})
    print('Diarization downloaded:',target)
(base/'download-info.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print('Models ready. The application runs with Hugging Face offline mode enabled.')
