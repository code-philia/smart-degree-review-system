"""Same-object bilingual captions keep one finding and every physical title box."""
from pathlib import Path
import unittest
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.model import PdfDocument, PdfPage, PdfLine

class BilingualCaptionTests(unittest.TestCase):
    def line(self,text,y,page=1,x=160,x2=440):
        return PdfLine(page,text,(x,y,x2,y+12),600,800)
    def run_rule(self,lines,rule):
        pages=tuple(PdfPage(n,600,800,tuple(l for l in lines if l.page_number==n)) for n in sorted({l.page_number for l in lines}))
        return detect_rules(build_index(PdfDocument(Path('fixture.pdf'),pages)),[rule])[str(rule)]['findings']
    def test_unreferenced_bilingual_figure_is_one_finding_with_both_boxes(self):
        lines=[self.line('图2.3 实验结果',300),self.line('Figure 2.3 Experimental results',317,x=100,x2=510)]
        findings=self.run_rule(lines,15)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['token'],'2.3')
        self.assertEqual(len(findings[0]['location']['rects']),2)
        self.assertEqual([(r['y1'],r['y2']) for r in findings[0]['location']['rects']],[(300,312),(317,329)])
        self.assertIn('Figure 2.3',findings[0]['text_excerpt'])
    def test_unreferenced_bilingual_table_is_one_finding_with_both_boxes(self):
        findings=self.run_rule([self.line('Table 4.2 Results',300),self.line('表4.2 实验结果',317)],16)
        self.assertEqual(len(findings),1)
        self.assertEqual(len(findings[0]['location']['rects']),2)
    def test_native_multiline_bilingual_caption_is_one_physical_finding(self):
        import tempfile
        import pymupdf
        from pdf_rules.engine import detect
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wrapped-caption.pdf'
            with pymupdf.open() as pdf:
                page=pdf.new_page(width=600,height=800)
                page.insert_text((160,300), '图2.3 多条件实验中的统计结果\n以及不同参数设置下的性能对比\n与误差分布分析',fontname='china-s',fontsize=12)
                page.insert_text((100,365),'Figure 2.3 Results across conditions',fontsize=12)
                pdf.save(path)
            findings=detect(path,[15])['rules']['15']['findings']
        self.assertEqual(len(findings),1)
        self.assertEqual(len(findings[0]['location']['rects']),2)
        self.assertIn('误差分布分析',findings[0]['text_excerpt'])

    def test_referenced_bilingual_figure_has_no_alarm(self):
        findings=self.run_rule([self.line('正文如图2.3所示。',100),self.line('图2.3 实验结果',300),self.line('Figure 2.3 Experimental results',317)],15)
        self.assertEqual(findings,[])
    def test_same_number_on_different_pages_is_not_silently_merged(self):
        findings=self.run_rule([self.line('图2.3 第一张图',300),self.line('Figure 2.3 Different figure',300,page=2)],15)
        self.assertEqual(len(findings),2)
    def test_distant_same_number_captions_are_distinct(self):
        findings=self.run_rule([self.line('图2.3 第一张图',180),self.line('Figure 2.3 Different figure',600)],15)
        self.assertEqual(len(findings),2)
    def test_nearby_different_numbers_keep_separate_findings(self):
        findings=self.run_rule([self.line('图2.3 图一',300),self.line('Figure 2.4 Other figure',317)],15)
        self.assertEqual([f['token'] for f in findings],['2.3','2.4'])
    def test_parallel_columns_are_distinct_objects(self):
        findings=self.run_rule([self.line('图2.3 左图',300,x=30,x2=240),self.line('Figure 2.3 Right figure',317,x=360,x2=570)],15)
        self.assertEqual(len(findings),2)
    def test_body_and_appendix_same_number_remain_distinct(self):
        lines=[self.line('图1.1 正文图',300),self.line('Figure 1.1 Body figure',317),self.line('附录A 实验',50,page=2),self.line('图1.1 附录图',300,page=2),self.line('Figure 1.1 Appendix figure',317,page=2)]
        findings=self.run_rule(lines,15)
        self.assertEqual([(f['page'],f['token']) for f in findings],[(1,'1.1'),(2,'1.1')])

if __name__=='__main__':unittest.main()


def mismatched_table_document(referenced=True):
    lines=[PdfLine(1,'表3.1 实验结果',(210,300,390,312),600,800,font_size=10.5,bold=True),
           PdfLine(1,'Figure 3.1 Experimental results',(120,318,480,330),600,800,font_size=10.5,bold=True)]
    if referenced:lines.insert(0,PdfLine(1,'结果如表3.1所示。',(80,100,500,115),600,800,font_size=12))
    return PdfDocument(Path('bilingual-labels.pdf'),(PdfPage(1,600,800,tuple(lines),tables=((80,345,520,460),)),))


def test_english_figure_label_of_a_real_chinese_table_creates_no_phantom_figure():
    doc=mismatched_table_document()
    result=detect_rules(build_index(doc),[15,16])
    assert result['15']['findings']==[]
    assert result['16']['findings']==[]


def test_an_unreferenced_real_table_with_conflicting_english_label_still_alarms():
    result=detect_rules(build_index(mismatched_table_document(False)),[15,16])
    assert result['15']['findings']==[]
    assert len(result['16']['findings'])==1
    assert len(result['16']['findings'][0]['location']['rects'])==2


def test_mismatched_bilingual_words_without_physical_evidence_cannot_invent_an_alias():
    from dataclasses import replace
    doc=mismatched_table_document()
    doc=PdfDocument(doc.path,(replace(doc.pages[0],tables=()),))
    assert detect_rules(build_index(doc),[15])['15']['findings']


def test_locative_body_citation_after_bilingual_title_is_not_a_third_caption():
    lines=(PdfLine(1,'图2.4 原生迁移时间流程',(220,342,390,354),600,840,font_size=10.5,bold=True),
           PdfLine(1,'Figure 2.4 Time Flow',(190,358,410,370),600,840,font_size=10.5,bold=True),
           PdfLine(1,'图2.4中，这对应多种步骤顺序执行的形态。',(85,391,525,405),600,840,font_size=12),
           PdfLine(1,'系统通过连续的数据交换执行完整迁移。',(85,417,525,431),600,840,font_size=12))
    doc=PdfDocument(Path('locative-citation.pdf'),(PdfPage(1,600,840,lines),))
    index=build_index(doc)
    assert len(index.figures)==2
    assert detect_rules(index,[15])['15']['findings']==[]


def test_country_enumeration_is_a_real_unreferenced_figure_caption():
    lines=(PdfLine(1,'图2.4 中、英文本结果比较',(180,342,420,354),600,840,font_size=10.5,bold=True),)
    doc=PdfDocument(Path('country-enumeration.pdf'),(PdfPage(1,600,840,lines),))
    findings=detect_rules(build_index(doc),[15])['15']['findings']
    assert len(findings)==1
    assert findings[0]['token']=='2.4'
