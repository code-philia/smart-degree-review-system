"""English archive regressions using the real native-text detector and Paper IR."""
from pathlib import Path
import sys
import tempfile
import unittest
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from paper_compiler.local_checks import core_parts, detect_ir
from fast_local_detector import native_coverage, load_ir
from five_rule_detector import Line, _rule_18
from test_fast_local_checks import sample_ir
from test_fast_punctuation_scope import paper


class EnglishLocalCompatibilityTests(unittest.TestCase):
    def test_barcode_only_blank_page_does_not_block_native_checks(self):
        ir = sample_ir()
        ir['root_id'] = 'paper'
        ir['layout']['pages'].append(dict(page_index=8, width=600, height=800,
                                         images=[[250, 740, 350, 770]], lines=[]))
        self.assertEqual(native_coverage(ir)['coverage']['pages']['status'], 'complete')

    def test_scanned_back_form_does_not_hide_missing_native_conclusion(self):
        ir = sample_ir()
        ir['root_id'] = 'paper'
        next(n for n in ir['nodes'] if n['id']=='conclusion-heading')['text'] = 'Chapter 3: Experiments'
        ir['layout']['pages'].append(dict(page_index=8,width=600,height=800,
                                         images=[[0,0,600,800]],lines=[]))
        self.assertEqual([f['token'] for f in detect_ir(native_coverage(ir),[34])['34']['findings']],['结论'])

    def test_unreadable_body_does_not_prove_a_chapter_is_missing(self):
        ir=sample_ir()
        ir['root_id']='paper'
        next(n for n in ir['nodes'] if n['id']=='conclusion-heading')['text']='Chapter 3: Experiments'
        ir['layout']['pages'][6].update(images=[[0,0,600,800]],lines=[])
        self.assertEqual(detect_ir(native_coverage(ir),[34])['34']['findings'],[])

    def test_scanned_back_form_does_not_prove_a_declaration_is_missing(self):
        ir=sample_ir()
        ir['root_id']='paper'
        ir['nodes']=[n for n in ir['nodes'] if n['id']!='originality']
        ir['layout']['pages'].append(dict(page_index=8,width=600,height=800,
                                         images=[[0,0,600,800]],lines=[]))
        self.assertEqual(detect_ir(native_coverage(ir),[34])['34']['findings'],[])

    def test_english_chapter_colon_headings_are_recognized(self):
        ir=sample_ir()
        next(n for n in ir['nodes'] if n['id']=='intro-heading')['text']='Chapter 1: Introduction'
        next(n for n in ir['nodes'] if n['id']=='conclusion-heading')['text']='Chapter 6: Conclusion'
        parts=core_parts(ir)
        self.assertTrue(parts['引言'])
        self.assertTrue(parts['结论'])
        self.assertEqual(detect_ir(ir,[34])['34']['findings'],[])

    def test_chinese_introduction_alias_remains_valid(self):
        ir=sample_ir()
        next(n for n in ir['nodes'] if n['id']=='intro-heading')['text']='第1章 简介'
        self.assertTrue(core_parts(ir)['引言'])

    def test_research_results_summary_is_conclusion_evidence(self):
        ir=sample_ir()
        next(n for n in ir['nodes'] if n['id']=='conclusion-heading')['text']='5.1 研究成果总结'
        self.assertTrue(core_parts(ir)['结论'])

    def test_chinese_closing_chapter_is_conclusion_evidence(self):
        ir=sample_ir()
        next(n for n in ir['nodes'] if n['id']=='conclusion-heading')['text']='第7章 结语'
        self.assertTrue(core_parts(ir)['结论'])

    def test_english_algorithm_fragments_are_not_prose(self):
        text='(Setup, KeyGen, Enc, Dec)：\nSetup(1)\n1. C0'
        self.assertEqual(detect_ir(paper(text),[35])['35']['findings'],[])

    def test_english_labels_and_quoted_dialogues_keep_their_punctuation(self):
        for text in ['Q：Is an apple present?',
                     'MotionGPT：A man stands with both hands raised.',
                     'DA: Delayed Allocation；TS: Timestamps；Log: Logging。',
                     'Banking_Report_2024.pdf；UNODC, Casinos and cryptocurrency.',
                     'USER: Please book it for Wednesday for 5 people.\nSYS : Reference number is：5NAWGJDC.']:
            with self.subTest(text=text):
                self.assertEqual(detect_ir(paper(text),[35])['35']['findings'],[])

    def test_english_label_does_not_hide_a_prose_comma_error(self):
        text='Result: The proposed method， improves detection accuracy.'
        self.assertEqual([f['token'] for f in detect_ir(paper(text),[35])['35']['findings']],['，'])

    def test_outline_mention_does_not_cut_off_the_body(self):
        ir=sample_ir()
        source=dict(next(n for n in ir['nodes'] if n['id']=='intro-heading')['provenance'][0])
        source.update(bbox=[60,200,300,212])
        ir['nodes'].append(dict(id='outline',kind='Paragraph',text='第5章 总结与展望',attrs={},
                                children=[],provenance=[source]))
        self.assertTrue(core_parts(ir)['主体'])

    def test_english_introduction_after_contents_is_body_evidence(self):
        for title in [('Chapter 1','Introduction'),('Chapter 1: Introduction',),
                      ('Chapter 1: Introduction and Contextualization',)]:
            with self.subTest(title=title), tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
                path=Path(folder)/'english-native.pdf'
                with pymupdf.open() as doc:
                    page=doc.new_page()
                    page.insert_text((70,100),'Contents',fontsize=20)
                    page.insert_text((70,150),'Introduction .............. 1',fontsize=12)
                    page.insert_text((70,175),'Methods ................... 2',fontsize=12)
                    page=doc.new_page()
                    for index,line in enumerate(title):page.insert_text((70,120+index*30),line,fontsize=20)
                    page.insert_text((70,220),'This paragraph introduces the study and its objectives.',fontsize=12)
                    page=doc.new_page();page.insert_text((70,120),'2 Methods',fontsize=20)
                    page.insert_text((70,160),'The study uses a reproducible local method.',fontsize=12)
                    doc.save(path)
                ir=load_ir(path)
                self.assertTrue(core_parts(ir)['引言'])
                self.assertTrue(any(n['kind']=='Paragraph' and n['text'] and
                                    'This paragraph introduces' in n['text'] for n in ir['nodes']))

    def formula(self,text,wrapped=False):
        lines=[Line(1,'(3–1)',(490,150,535,165),600,800)]
        if wrapped:
            lines.extend([Line(1,'The result follows Eq.',(60,200,400,215),600,800),
                          Line(1,text,(60,220,400,235),600,800)])
        else:
            lines.append(Line(1,text,(60,200,450,215),600,800))
        return _rule_18(lines)

    def test_bare_english_formula_reference_matches_existing_target(self):
        self.assertEqual(self.formula('The result follows Eq. 3–1.')['findings'],[])

    def test_bare_english_formula_reference_reports_missing_target(self):
        findings=self.formula('The result follows Equation 3–99.')['findings']
        self.assertEqual([f['token'] for f in findings],['3–99'])

    def test_wrapped_bare_formula_reference_reports_missing_target(self):
        findings=self.formula('3–99, which defines the result.',wrapped=True)['findings']
        self.assertEqual([f['token'] for f in findings],['3–99'])

    def test_normal_english_words_are_not_formula_references(self):
        self.assertEqual(self.formula('The sequence 399 has a frequency of 2.')['findings'],[])

    def test_bare_code_identifiers_and_algebra_are_not_chapter_references(self):
        for text in ['try_rewrite EQ1; try_rewrite EQ2;',
                     'Given the equation 4x + 2y = 10, compute the solution.',
                     'The illustrative example contains (Eq. 2).',
                     'The example uses Boltzmann selection (eq.3).']:
            with self.subTest(text=text):
                self.assertEqual(self.formula(text)['findings'],[])

    def test_complete_formula_sentence_is_not_joined_to_a_numeric_next_line(self):
        lines=[Line(1,'(3–1)',(490,150,535,165),600,800),
               Line(1,'This result follows Eq. 3–1.',(60,200,450,215),600,800),
               Line(1,'2 independent experiments verify the result.',(60,220,450,235),600,800)]
        self.assertEqual(_rule_18(lines)['findings'],[])

    def test_english_formula_range_expands_en_dash_chapter_numbers(self):
        lines=[Line(1,f'(3–{n})',(490,100+n*10,535,110+n*10),600,800) for n in [22,23,24]]
        lines.append(Line(1,'The result is formalized in Eq. 3–22 - 3–24.',(60,500,450,515),600,800))
        self.assertEqual(_rule_18(lines)['findings'],[])

    def test_formula_number_split_after_a_dash_is_not_truncated(self):
        lines=[Line(1,'(2–2)',(490,150,535,165),600,800),
               Line(1,'The tanh function is expressed in equation 2–',(60,200,450,215),600,800),
               Line(1,'2, which defines the result.',(60,220,450,235),600,800)]
        self.assertEqual(_rule_18(lines)['findings'],[])

    def test_english_prose_reports_chinese_punctuation(self):
        for token in '，；：！？。':
            with self.subTest(token=token):
                text=f'The proposed method{token} improves detection accuracy.'
                findings=detect_ir(paper(text),[35])['35']['findings']
                self.assertEqual(len(findings),1)
                self.assertEqual(findings[0]['token'],token)
                self.assertIn('误用了中文',findings[0]['message'])

    def test_correct_english_punctuation_is_clean(self):
        text='The proposed method, which is local, improves detection accuracy.'
        self.assertEqual(detect_ir(paper(text),[35])['35']['findings'],[])

    def test_single_letter_english_words_do_not_hide_punctuation_errors(self):
        for text in ['We use a local model。','This is a valid result。']:
            with self.subTest(text=text):
                self.assertEqual([f['token'] for f in detect_ir(paper(text),[35])['35']['findings']],['。'])

    def test_english_numeric_results_still_check_chinese_punctuation(self):
        for text,token in [('The final value is 5。','。'),
                           ('The measured accuracy is 95%， which confirms the reported improvement.','，')]:
            with self.subTest(text=text):
                self.assertEqual([f['token'] for f in detect_ir(paper(text),[35])['35']['findings']],[token])

    def test_english_terms_in_chinese_prose_keep_chinese_punctuation(self):
        self.assertEqual(detect_ir(paper('使用 Python，Java 和 C++ 完成实验。'),[35])['35']['findings'],[])

    def test_quoted_english_data_is_not_a_punctuation_violation(self):
        self.assertEqual(detect_ir(paper('The recorded input is "method，result" in this experiment.'),[35])['35']['findings'],[])


if __name__=='__main__':
    unittest.main()
