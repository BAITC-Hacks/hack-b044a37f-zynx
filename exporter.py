"""UTF-8 JSON plus local DOCX/PDF exports. No external conversion services."""
from io import BytesIO
from pathlib import Path
from html import escape
import os

def docx_bytes(meeting):
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.oxml.ns import qn
    doc=Document()
    section=doc.sections[0]
    section.top_margin=section.bottom_margin=Cm(1.8)
    section.left_margin=section.right_margin=Cm(2)
    normal=doc.styles['Normal']; normal.font.name='Arial'; normal.font.size=Pt(10)
    for style in doc.styles:
        if style.type == 1:
            style.font.name='Arial'; style.font.color.rgb=RGBColor(0,0,0)
            style.font.color.theme_color=None
            if style.element.pPr is not None:
                for border in list(style.element.pPr.findall(qn('w:pBdr'))): style.element.pPr.remove(border)
    doc.styles['Title'].font.size=Pt(24)
    doc.add_heading('Протокол совещания',0)
    doc.add_paragraph('ZYNX Minutes')
    doc.add_heading(meeting['title'],1)
    doc.add_paragraph(f"Дата: {meeting['date']}  |  Режим: {'Локальный AI' if meeting['mode']=='local' else 'Правила без AI'}")
    doc.add_paragraph('Черновик протокола. Сверьте содержание с исходной записью.')
    doc.add_heading('Краткое содержание',1); doc.add_paragraph(meeting['result']['summary'])
    if meeting['result'].get('decisions'):
        doc.add_heading('Решения',1)
        for item in meeting['result']['decisions']: doc.add_paragraph(item,style='List Bullet')
    doc.add_heading('Поручения',1)
    for i,t in enumerate(meeting['result']['tasks'],1):
        doc.add_heading(f"{i}. {t['task']}",2)
        doc.add_paragraph(f"Ответственный: {t['owner']}\nСрок: {t['due_text']}\nКалендарная дата: {t.get('due_date') or 'Уточнить'}\nСтатус: {t['status']}\nПроверено человеком: {'Да' if t.get('reviewed') else 'Нет'}")
        doc.add_paragraph('Основание: '+t.get('evidence',''))
        if t.get('issues'): doc.add_paragraph('Проверка: '+'; '.join(t['issues']))
    doc.add_heading('Транскрипт',1)
    for turn in meeting['turns']:
        p=doc.add_paragraph(); p.add_run(f"[{turn['id']}] {turn['speaker']}: ").bold=True; p.add_run(turn['text'])
    out=BytesIO(); doc.save(out); return out.getvalue()

def pdf_bytes(meeting):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    candidates=[os.environ.get('ZYNX_FONT',''),'C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/Library/Fonts/Arial.ttf']
    font=next((p for p in candidates if p and Path(p).is_file()),None)
    if not font: raise ValueError('Для PDF нужен шрифт с кириллицей. Задайте ZYNX_FONT или скачайте DOCX.')
    pdfmetrics.registerFont(TTFont('Zynx',font))
    styles=getSampleStyleSheet()
    for s in styles.byName.values(): s.fontName='Zynx'
    styles['Normal'].fontSize=9; styles['Normal'].leading=14
    styles['Heading1'].fontSize=17; styles['Heading1'].leading=23
    styles['Heading2'].fontSize=11; styles['Heading2'].leading=16
    output=BytesIO(); doc=SimpleDocTemplate(output,leftMargin=45,rightMargin=45,topMargin=42,bottomMargin=42)
    story=[]
    def add(text,style='Normal'):
        story.append(Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])); story.append(Spacer(1,7))
    add('Протокол совещания','Title'); add('ZYNX Minutes'); add(meeting['title'],'Heading1')
    add(f"Дата: {meeting['date']} | Режим: {'Локальный AI' if meeting['mode']=='local' else 'Правила без AI'}")
    add('Черновик. Проверьте содержание перед утверждением.')
    add('Краткое содержание','Heading1'); add(meeting['result']['summary'])
    if meeting['result'].get('decisions'):
        add('Решения','Heading1')
        for item in meeting['result']['decisions']: add('• '+item)
    add('Поручения','Heading1')
    for i,t in enumerate(meeting['result']['tasks'],1):
        add(f"{i}. {t['task']}",'Heading2')
        add(f"Ответственный: {t['owner']}\nСрок: {t['due_text']} | Дата: {t.get('due_date') or 'Уточнить'}\nСтатус: {t['status']} | Проверено: {'Да' if t.get('reviewed') else 'Нет'}")
        add('Основание: '+t.get('evidence',''))
        if t.get('issues'): add('Проверка: '+'; '.join(t['issues']))
    add('Транскрипт','Heading1')
    for t in meeting['turns']: add(f"[{t['id']}] {t['speaker']}: {t['text']}")
    def footer(canvas,document):
        canvas.setFont('Zynx',8); canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(45,23,'ZYNX • Локальная обработка'); canvas.drawRightString(550,23,str(document.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
