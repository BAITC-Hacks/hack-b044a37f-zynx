"""Transcript parsing, conservative deadlines, evidence validation; no network."""
from __future__ import annotations
from datetime import date, timedelta
import re
import uuid

UNKNOWN = 'Не указан'
MONTHS = {'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12,'қаңтар':1,'ақпан':2,'наурыз':3,'сәуір':4,'мамыр':5,'маусым':6,'шілде':7,'тамыз':8,'қыркүйек':9,'қазан':10,'қараша':11,'желтоқсан':12}

def parse_transcript(text: str) -> list[dict]:
    """One turn per line; explicit speaker names are preserved, never inferred."""
    turns = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        match = re.match(r'^([^:\n]{1,80}):\s*(.+)$', raw)
        speaker, body = (match[1].strip(), match[2]) if match else ('Не определён', raw)
        turns.append({'id':len(turns)+1, 'speaker':speaker, 'text':body, 'start':None, 'end':None})
    return turns

def deadline(phrase: str, meeting_date: str) -> tuple[str | None, str]:
    """Do not let a model invent absolute dates. Preserve unresolved text."""
    base = date.fromisoformat(meeting_date)
    p = (phrase or '').lower().strip().rstrip('.')
    if not p or p in ['не указан','не указано','белгісіз','көрсетілмеген']:
        return None, 'Срок не назван'
    m = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', p)
    if m:
        try:
            return date.fromisoformat(m[1]).isoformat(), ''
        except ValueError:
            return None, 'Некорректная дата'
    m = re.search(r'\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b', p)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat(), ''
        except ValueError:
            return None, 'Некорректная дата'
    for word, month in MONTHS.items():
        m = re.search(r'\b(\d{1,2})\s+' + word, p)
        if m:
            year = re.search(r'\b(20\d{2})\b', p)
            try:
                d = date(int(year[1]) if year else base.year, month, int(m[1]))
            except ValueError:
                return None, 'Некорректная дата'
            if not year and d < base:
                return None, 'Уточните год: дата без года раньше совещания'
            return d.isoformat(), '' if year else 'Год взят из даты совещания; подтвердите'
    if p in ['завтра','ертең','до завтра','к завтрашнему дню']:
        return (base + timedelta(days=1)).isoformat(), ''
    if p in ['сегодня','бүгін','до конца дня']:
        return base.isoformat(), ''
    m = re.search(r'(?:через|за|в течение)\s+(\d+|одну|две|три|один|два|три)\s+(недел\w*|дн\w*|день)', p)
    if m:
        n = int(m[1]) if m[1].isdigit() else {'одну':1,'две':2,'три':3,'один':1,'два':2}[m[1]]
        return (base + timedelta(days=n*(7 if m[2].startswith('недел') else 1))).isoformat(), 'Отсчёт от даты совещания; календарные дни'
    m = re.search(r'(\d+|бір|екі|үш)\s+(күн|апта)\s*(?:ішінде|кейін)', p)
    if m:
        n = int(m[1]) if m[1].isdigit() else {'бір':1,'екі':2,'үш':3}[m[1]]
        return (base + timedelta(days=n*(7 if m[2]=='апта' else 1))).isoformat(), 'Отсчёт от даты совещания; календарные дни'
    # End of week, weekdays, business days, and event-based deadlines need policy.
    return None, 'Нужно уточнить календарную дату'

def normalize(s: str) -> str:
    return ' '.join(s.lower().split())

def validate_result(raw: dict, turns: list[dict], meeting_date: str) -> dict:
    """Enforce exact provenance and flag any unsupported or missing fields."""
    if not isinstance(raw, dict) or not isinstance(raw.get('tasks'), list):
        raise ValueError('Модель не вернула список tasks. Повторите обработку.')
    result = {'summary':str(raw.get('summary',''))[:6000], 'decisions':[str(x)[:1000] for x in raw.get('decisions',[])][:30], 'tasks':[], 'warnings':[]}
    by_id = {t['id']:t for t in turns}
    seen = set()
    for item in raw['tasks'][:80]:
        if not isinstance(item, dict) or not str(item.get('task','')).strip():
            continue
        task = str(item['task'])[:2000]
        ids = [i for i in item.get('source_ids',[]) if isinstance(i,int) and i in by_id]
        quote = str(item.get('evidence','')).strip()[:3000]
        corpus = ' '.join(by_id[i]['text'] for i in ids)
        issues = []
        if not ids or not quote or normalize(quote) not in normalize(corpus):
            issues.append('Цитата не подтверждена указанными репликами')
        owner = str(item.get('owner') or UNKNOWN).strip()[:200]
        # Evidence may include a speaker label when the speaker accepts work.
        source_context = ' '.join(by_id[i]['speaker']+': '+by_id[i]['text'] for i in ids)
        if owner == UNKNOWN:
            issues.append('Ответственный не назван')
        elif normalize(owner) not in normalize(source_context):
            issues.append('Ответственного нужно подтвердить по контексту')
        due_text = str(item.get('due_text') or UNKNOWN)[:250]
        if due_text != UNKNOWN and normalize(due_text) not in normalize(corpus):
            issues.append('Формулировка срока не найдена в источнике')
            due_date, note = None, 'Срок не подтверждён цитатой'
        else:
            due_date, note = deadline(due_text, meeting_date)
        if note:
            issues.append(note)
        key = (normalize(task), normalize(owner), normalize(due_text))
        if key in seen:
            continue
        seen.add(key)
        result['tasks'].append({'id':uuid.uuid4().hex[:12], 'task':task, 'owner':owner, 'due_text':due_text, 'due_date':due_date, 'evidence':quote, 'source_ids':ids, 'issues':issues, 'status':'В работе', 'reviewed':False})
    return result

def rule_preview(turns: list[dict], meeting_date: str) -> dict:
    """Explicit, limited non-AI fallback; only accepts stated assignments."""
    tasks = []
    for t in turns:
        # Demo-friendly format also works for any explicitly structured new text.
        for sentence in re.split(r'[.!?]\s+', t['text']):
            m = re.search(r'(.+?)\s*[—–;]\s*(?:ответственн\w*|жауапты)\s*[:—–]?\s*([^;]+);\s*(?:срок|мерзім)\s*[:—–]?\s*(.+)', sentence, re.I)
            if m:
                tasks.append({'task':m[1].strip(), 'owner':m[2].strip(), 'due_text':m[3].strip().rstrip('.'), 'source_ids':[t['id']], 'evidence':sentence})
    raw = {'summary':f'Режим правил: найдено явно оформленных поручений — {len(tasks)}. Для смыслового анализа свободной речи выберите локальный AI.', 'decisions':[], 'tasks':tasks}
    result = validate_result(raw, turns, meeting_date)
    result['warnings'] = ['Это разбор по правилам, без AI. Он не заменяет распознавание аудио, диаризацию и смысловой анализ.']
    return result

def align_words(segments: list[dict], diarization: list[dict]) -> list[dict]:
    """Word timestamps prevent a long ASR segment assigning two voices to one person."""
    words = []
    for segment in segments:
        words.extend(segment.get('words') or [{'start':segment['start'],'end':segment['end'],'word':segment['text']}])
    turns = []
    for w in words:
        overlaps = [(max(0, min(w['end'],d['end'])-max(w['start'],d['start'])),d['speaker']) for d in diarization]
        overlap, speaker = max(overlaps, default=(0,'Не определён'))
        if overlap <= 0:
            speaker = 'Не определён'
        if turns and turns[-1]['speaker']==speaker and w['start']-turns[-1]['end'] < 2:
            turns[-1]['text'] += w['word']
            turns[-1]['end'] = w['end']
        else:
            turns.append({'id':len(turns)+1,'speaker':speaker,'text':w['word'],'start':w['start'],'end':w['end']})
    for t in turns:
        t['text'] = t['text'].strip()
    return turns
