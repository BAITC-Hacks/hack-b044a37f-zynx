import unittest
from core import deadline, parse_transcript, validate_result, rule_preview, align_words
from unittest.mock import patch
from agent import analyze

class CoreTests(unittest.TestCase):
    def test_relative_date_uses_meeting_date(self):
        self.assertEqual(deadline('через две недели','2026-09-23')[0],'2026-10-07')
        self.assertEqual(deadline('екі апта ішінде','2026-09-23')[0],'2026-10-07')
    def test_unknown_deadline_stays_unknown(self):
        for phrase in ['Не указан','после совещания','до конца недели','к среде','через 5 рабочих дней']:
            self.assertIsNone(deadline(phrase,'2026-09-23')[0])
    def test_invalid_and_past_date_without_year(self):
        self.assertIsNone(deadline('31 февраля','2026-09-23')[0])
        self.assertIsNone(deadline('1 января','2026-09-23')[0])
        self.assertEqual(deadline('25 қыркүйекке дейін','2026-09-23')[0],'2026-09-25')
    def test_no_invented_speaker(self):
        turns=parse_transcript('Текст без имени\nДана: Ертең жіберемін.')
        self.assertEqual(turns[0]['speaker'],'Не определён')
        self.assertEqual(turns[1]['speaker'],'Дана')
    def test_evidence_and_hallucinated_deadline_flagged(self):
        turns=parse_transcript('Дана: Подготовлю отчёт.')
        raw={'tasks':[{'task':'Отчёт','owner':'Дана','due_text':'завтра','source_ids':[1],'evidence':'несуществующая цитата'}]}
        task=validate_result(raw,turns,'2026-09-23')['tasks'][0]
        self.assertIsNone(task['due_date'])
        self.assertTrue(any('Цитата' in x for x in task['issues']))
        self.assertTrue(any('срока' in x for x in task['issues']))
    def test_word_alignment_splits_speakers(self):
        segments=[{'start':0,'end':4,'text':'Привет Да','words':[{'start':0,'end':1,'word':' Привет'},{'start':2,'end':3,'word':' Да'}]}]
        diar=[{'start':0,'end':1.5,'speaker':'A'},{'start':1.5,'end':4,'speaker':'B'}]
        turns=align_words(segments,diar)
        self.assertEqual([x['speaker'] for x in turns],['A','B'])
        self.assertEqual(turns[1]['text'],'Да')
    def test_no_overlap_not_assigned(self):
        turns=align_words([{'start':0,'end':1,'text':'Текст'}],[{'start':3,'end':4,'speaker':'A'}])
        self.assertEqual(turns[0]['speaker'],'Не определён')
    def test_rules_apply_to_new_input(self):
        turns=parse_transcript('Олег: Купить бумагу — ответственный Нина; срок 2026-11-11.')
        result=rule_preview(turns,'2026-09-23')
        self.assertEqual(result['tasks'][0]['owner'],'Нина')
        self.assertEqual(result['tasks'][0]['due_date'],'2026-11-11')
        self.assertTrue(result['warnings'])
    def test_questions_not_extracted_by_rules(self):
        self.assertEqual(rule_preview(parse_transcript('Олег: Может быть, купим бумагу?'),'2026-09-23')['tasks'],[])
    def test_verifier_result_used(self):
        turns=parse_transcript('Дана: Отчёт подготовлю 25 сентября.')
        draft={'summary':'Черновик','decisions':[],'tasks':[]}
        reviewed={'summary':'Проверено','decisions':[],'tasks':[{'task':'Отчёт','owner':'Дана','due_text':'25 сентября','source_ids':[1],'evidence':'Отчёт подготовлю 25 сентября.'}]}
        steps=[]
        with patch('agent.request_model',side_effect=[draft,reviewed]) as model:
            result=analyze(turns,'2026-09-23','qwen3:8b',steps.append)
        self.assertEqual(model.call_count,2)
        self.assertEqual(result['tasks'][0]['due_date'],'2026-09-25')
        self.assertEqual(len(steps),3)

if __name__=='__main__': unittest.main()
