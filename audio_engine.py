"""All inference is local. Models must be downloaded before processing a meeting."""
import os
from pathlib import Path
from functools import lru_cache
from core import align_words

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
BASE = Path(__file__).resolve().parent

@lru_cache(maxsize=1)
def whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Установите аудиомодуль: python -m pip install -r requirements-audio.txt') from exc
    path = os.environ.get('ZYNX_WHISPER_PATH',str(BASE/'models/whisper-small'))
    if not Path(path).is_dir():
        raise RuntimeError('Модель Whisper не найдена. Выполните: python scripts/download_models.py --whisper small')
    device = os.environ.get('ZYNX_DEVICE','cpu')
    return WhisperModel(path,device=device,compute_type='float16' if device=='cuda' else 'int8',local_files_only=True)

@lru_cache(maxsize=1)
def speaker_model():
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError('Установите диаризацию: python -m pip install -r requirements-diarization.txt') from exc
    path = os.environ.get('ZYNX_DIARIZATION_PATH',str(BASE/'models/diarization'))
    if not Path(path).is_dir():
        raise RuntimeError('Модель диаризации не найдена. См. README → подготовка моделей.')
    model = Pipeline.from_pretrained(path)
    if os.environ.get('ZYNX_DEVICE','cpu')=='cuda':
        import torch
        model.to(torch.device('cuda'))
    return model

def transcribe(path, use_diarization, speaker_count, language, progress):
    from faster_whisper import decode_audio
    if speaker_count < 0 or speaker_count > 20:
        raise ValueError('Количество голосов должно быть от 0 до 20.')
    waveform = decode_audio(str(path),sampling_rate=16000)
    if len(waveform)>16000*600:
        raise ValueError('Для MVP запись должна быть не длиннее 10 минут.')
    progress('Распознавание речи на этом компьютере')
    segments, info = whisper_model().transcribe(waveform,language=language if language in ('ru','kk') else None,multilingual=language=='mixed',beam_size=5,vad_filter=True,word_timestamps=True,condition_on_previous_text=False)
    items=[]
    for s in segments:
        items.append({'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]})
    if not items:
        raise ValueError('Речь не обнаружена. Проверьте запись.')
    if use_diarization:
        progress('Диаризация: определение голосов и привязка слов')
        import torch
        options = {'num_speakers':speaker_count} if speaker_count else {}
        output = speaker_model()({'waveform':torch.from_numpy(waveform).unsqueeze(0),'sample_rate':16000},**options)
        annotation = output.exclusive_speaker_diarization
        diar=[]
        if hasattr(annotation,'itertracks'):
            for turn, _, label in annotation.itertracks(yield_label=True):
                diar.append({'start':turn.start,'end':turn.end,'speaker':label})
        else:
            for turn,label in annotation:
                diar.append({'start':turn.start,'end':turn.end,'speaker':label})
        turns=align_words(items,diar)
    else:
        turns=[{'id':i+1,'speaker':'Не определён','text':s['text'].strip(),'start':s['start'],'end':s['end']} for i,s in enumerate(items)]
    return {'turns':turns,'language':info.language,'diarized':use_diarization}
