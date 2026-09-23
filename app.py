"""Local single-user application. Launch: python app.py (Python 3.11+)."""
from __future__ import annotations
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import urllib.parse
import uuid
from core import parse_transcript, rule_preview

BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get('ZYNX_DATA_DIR',str(BASE/'data')))
TOKEN=secrets.token_urlsafe(24)
JOBS={}
JOBS_LOCK=threading.Lock()
POOL=ThreadPoolExecutor(max_workers=1)
MAX_BODY=28*1024*1024

def database():
    DATA.mkdir(exist_ok=True,parents=True)
    db=sqlite3.connect(DATA/'meetings.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    return db

def save(meeting):
    with database() as db:
        db.execute('INSERT OR REPLACE INTO meetings VALUES (?,?)',(meeting['id'],json.dumps(meeting,ensure_ascii=False)))

def load(ident):
    with database() as db: row=db.execute('SELECT body FROM meetings WHERE id=?',(ident,)).fetchone()
    if not row: raise ValueError('Совещание не найдено')
    return json.loads(row[0])

def progress(job_id,message):
    with JOBS_LOCK:
        JOBS[job_id]['message']=message
        JOBS[job_id]['steps'].append(message)

def worker(job_id,kind,payload):
    try:
        if kind=='transcribe':
            suffix=Path(payload.get('filename','audio.wav')).suffix.lower()
            if suffix not in ['.wav','.mp3','.m4a','.ogg','.flac','.webm','.mp4']:
                raise ValueError('Неподдерживаемый формат аудио')
            content=base64.b64decode(payload.get('audio',''),validate=True)
            if not content or len(content)>20*1024*1024: raise ValueError('Аудио: от 1 байта до 20 МБ')
            with tempfile.TemporaryDirectory(prefix='zynx-') as tmp:
                path=Path(tmp)/('recording'+suffix); path.write_bytes(content)
                try:
                    from audio_engine import transcribe
                    output=transcribe(path,bool(payload.get('diarize',True)),int(payload.get('speaker_count',0)),payload.get('language','mixed'),lambda m:progress(job_id,m))
                except ImportError as exc:
                    raise RuntimeError('Установите requirements-audio.txt и requirements-diarization.txt; см. README.') from exc
            answer=output
        else:
            title=str(payload.get('title','Совещание')).strip()[:200] or 'Совещание'
            meeting_date=str(payload.get('date',date.today().isoformat()))
            date.fromisoformat(meeting_date)
            transcript=str(payload.get('transcript','')).strip()
            if not transcript or len(transcript)>26000: raise ValueError('Введите транскрипт от 1 до 26 000 символов')
            turns=payload.get('turns')
            if turns is None:
                turns=parse_transcript(transcript)
            else:
                if not isinstance(turns,list) or len(turns)>3000: raise ValueError('Некорректный список реплик')
                turns=[{'id':i+1,'speaker':str(t.get('speaker','Не определён'))[:80], 'text':str(t.get('text','')),'start':t.get('start'),'end':t.get('end')} for i,t in enumerate(turns)]
                # Client only submits these if transcript was not edited after ASR.
                if sum(len(t['text']) for t in turns)>26000: raise ValueError('Транскрипт слишком длинный')
            mode=payload.get('mode','rules')
            if mode=='local':
                from agent import analyze
                result=analyze(turns,meeting_date,str(payload.get('model','qwen3:8b')),lambda m:progress(job_id,m))
            elif mode=='rules':
                progress(job_id,'Разбор явно оформленных поручений по правилам (без AI)')
                result=rule_preview(turns,meeting_date)
            else: raise ValueError('Неизвестный режим')
            answer={'id':uuid.uuid4().hex,'title':title,'date':meeting_date,'mode':mode,'turns':turns,'result':result,'created_at':datetime.now().isoformat(),'trace':JOBS[job_id]['steps'].copy()}
            save(answer)
        with JOBS_LOCK: JOBS[job_id].update(state='done',result=answer,message='Готово')
    except Exception as exc:
        with JOBS_LOCK: JOBS[job_id].update(state='error',message=str(exc))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,body,status=200,ctype='application/json; charset=utf-8',filename=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
        elif isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'")
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(body)
    def valid_host(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        return self.headers.get('Host') in allowed
    def do_GET(self):
        if not self.valid_host(): return self.send({'error':'Invalid Host'},403)
        path=urllib.parse.urlsplit(self.path).path
        try:
            if path in ['/','/style.css','/app.js']:
                name={'/':'index.html','/style.css':'style.css','/app.js':'app.js'}[path]
                return self.send((BASE/'web'/name).read_bytes(),ctype={'/':'text/html; charset=utf-8','/style.css':'text/css','/app.js':'text/javascript; charset=utf-8'}[path])
            if path=='/api/config':
                return self.send({'csrf':TOKEN,'whisper':(BASE/'models/whisper-small').is_dir() or Path(os.environ.get('ZYNX_WHISPER_PATH','__none__')).is_dir(),'diarization':(BASE/'models/diarization').is_dir() or Path(os.environ.get('ZYNX_DIARIZATION_PATH','__none__')).is_dir(),'export':bool(importlib.util.find_spec('docx') and importlib.util.find_spec('reportlab'))})
            if path=='/api/examples':
                return self.send(json.loads((BASE/'examples/demo.json').read_text(encoding='utf-8')))
            if path=='/api/meetings':
                with database() as db: rows=db.execute('SELECT body FROM meetings ORDER BY rowid DESC LIMIT 100').fetchall()
                items=[json.loads(r[0]) for r in rows]
                return self.send([{'id':m['id'],'title':m['title'],'date':m['date'],'count':len(m['result']['tasks'])} for m in items])
            if path.startswith('/api/jobs/'):
                ident=path.rsplit('/',1)[1]
                with JOBS_LOCK: job=JOBS.get(ident,{'state':'error','message':'Задание не найдено'})
                return self.send(job)
            m=re.fullmatch(r'/api/meetings/([a-f0-9]{32})(?:/(json|docx|pdf))?',path)
            if m:
                meeting=load(m[1]); fmt=m[2]
                if fmt=='json': return self.send(meeting,filename='protocol.json')
                if fmt in ['docx','pdf']:
                    from exporter import docx_bytes,pdf_bytes
                    data=docx_bytes(meeting) if fmt=='docx' else pdf_bytes(meeting)
                    return self.send(data,ctype='application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename='protocol.'+fmt)
                return self.send(meeting)
            self.send({'error':'Не найдено'},404)
        except ImportError:
            self.send({'error':'Установите экспорт: python -m pip install -r requirements.txt'},400)
        except Exception as exc: self.send({'error':str(exc)},400)
    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Zynx-Token')!=TOKEN:
            return self.send({'error':'Обновите страницу приложения'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>MAX_BODY: return self.send({'error':'Слишком большой запрос'},413)
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict): raise ValueError('Ожидался объект JSON')
            if self.path in ['/api/analyze','/api/transcribe']:
                if self.path=='/api/transcribe' and payload.get('consent') is not True:
                    raise ValueError('Подтвердите согласие участников или использование синтетической записи')
                with JOBS_LOCK:
                    if any(j['state']=='running' for j in JOBS.values()): return self.send({'error':'Дождитесь завершения текущей обработки'},409)
                    # Keep recent job results only; meetings remain in SQLite.
                    for key in list(JOBS)[:-10]: JOBS.pop(key,None)
                    ident=uuid.uuid4().hex; JOBS[ident]={'state':'running','message':'Подготовка','steps':[]}
                POOL.submit(worker,ident,'transcribe' if self.path.endswith('transcribe') else 'analyze',payload)
                return self.send({'job_id':ident},202)
            if self.path=='/api/save':
                meeting=load(str(payload.get('id','')))
                tasks=payload.get('tasks',[])
                if not isinstance(tasks,list) or len(tasks)!=len(meeting['result']['tasks']): raise ValueError('Некорректный список поручений')
                updates={t['id']:t for t in tasks}
                for task in meeting['result']['tasks']:
                    item=updates[task['id']]
                    task.update({k:str(item.get(k,task[k]))[:2000] for k in ['task','owner','due_text']})
                    value=item.get('due_date') or None
                    if value: date.fromisoformat(value)
                    task['due_date']=value
                    status=item.get('status','В работе')
                    if status not in ['В работе','Выполнено']: raise ValueError('Некорректный статус')
                    task['status']=status; task['reviewed']=bool(item.get('reviewed',False))
                meeting['result']['summary']=str(payload.get('summary',meeting['result']['summary']))[:6000]
                meeting['updated_at']=datetime.now().isoformat(); save(meeting)
                return self.send(meeting)
            if self.path=='/api/delete':
                with database() as db: db.execute('DELETE FROM meetings WHERE id=?',(str(payload.get('id','')),))
                return self.send({'ok':True})
            self.send({'error':'Не найдено'},404)
        except Exception as exc: self.send({'error':str(exc)},400)

if __name__=='__main__':
    port=int(os.environ.get('ZYNX_PORT','8765'))
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'ZYNX Minutes: http://127.0.0.1:{port} — Ctrl+C to stop',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
