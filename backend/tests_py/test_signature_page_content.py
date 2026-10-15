"""Scanned administrative continuations must not hide faint research content."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import random,tempfile,unittest
import pymupdf
from pdf_rules.layout_context import research_document
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.pdf_extract import extract_pdf

FIELDS="答辩委员会工作职务 姓名 职称 工作单位 签名 主席 委员 委员 委员 委员 秘书"

class SignaturePageContentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/"paper.pdf"

    def document(self, *, noise=False, text=None, fontsize=6, gray=.87, graphic=False, position=(60,650), rotate=0):
        source=pymupdf.open();page=source.new_page(width=600,height=800)
        page.draw_rect(page.rect,fill=(.994,)*3,color=None)
        page.insert_text((60,100),"Committee signature table",fontsize=12)
        if noise:
            rng=random.Random(1907)
            for _ in range(20):
                x=rng.uniform(25,565);y=rng.uniform(350,750)
                page.draw_circle((x,y),rng.uniform(.3,1.2),fill=(rng.uniform(.94,.995),)*3,color=None)
        if text:
            page.insert_text(position,text,rotate=rotate,fontsize=fontsize,fontname="china-s" if any(ord(c)>127 for c in text) else "helv",color=(gray,)*3)
        if graphic:page.draw_rect((100,500,220,610),fill=(.87,)*3,color=None)
        png=page.get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes("png");source.close()
        pdf=pymupdf.open();pdf.new_page(width=600,height=800)
        pdf.new_page(width=600,height=800).insert_image((0,0,600,800),stream=png)
        pdf.save(self.path);pdf.close()
        scanned=extract_pdf(self.path).pages[1]
        table=PdfLine(2,FIELDS,(60,80,540,275),600,800,source="mineru",role="table_body")
        scanned=replace(scanned,lines=(table,))
        form=PdfPage(1,600,800,(PdfLine(1,"答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名",(60,80,540,700),600,800,source="mineru",role="table_body"),))
        return PdfDocument(self.path,(form,scanned))

    def test_unresolved_scan_tail_is_not_accepted_as_blank(self):
        doc=self.document(noise=True)
        before=sha256(self.path.read_bytes()).hexdigest()
        self.assertGreater(doc.pages[1].ink_bottom,300)
        self.assertTrue(research_document(doc).pages[1].unreadable)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(),before)

    def test_faint_small_references_below_full_signature_table_remain_unread(self):
        for gray in (.87,.98,.99):
            for fontsize in (4,6,12):
                for text in ("See Figure 9.9.","附录Z","图9.9","图1","表1"):
                    with self.subTest(gray=gray,fontsize=fontsize,text=text):
                        if self.path.exists():self.path.unlink()
                        doc=self.document(text=text,gray=gray,fontsize=fontsize)
                        self.assertTrue(research_document(doc).pages[1].unreadable)

    def test_an_unread_graphic_below_signature_table_is_not_blank(self):
        self.assertTrue(research_document(self.document(graphic=True)).pages[1].unreadable)

    def test_noise_handling_requires_verified_preceding_form(self):
        doc=self.document(noise=True)
        self.assertTrue(research_document(PdfDocument(doc.path,(doc.pages[1],))).pages[0].unreadable)

    def test_sparse_secretary_text_does_not_enable_noise_exclusion(self):
        doc=self.document(noise=True)
        sparse=replace(doc.pages[1],lines=(PdfLine(2,"秘书 李同学 计算机学院",(60,65,540,110),600,800),))
        self.assertTrue(research_document(PdfDocument(doc.path,(doc.pages[0],sparse))).pages[1].unreadable)

    def test_recognized_reference_on_signature_page_is_preserved(self):
        doc=self.document(noise=True)
        line=PdfLine(2,"相关结果详见附录Z。",(60,300,540,320),600,800,source="mineru")
        page=replace(doc.pages[1],lines=(*doc.pages[1].lines,line))
        self.assertTrue(research_document(PdfDocument(doc.path,(doc.pages[0],page))).pages[1].unreadable)

    def test_short_references_at_other_positions_and_orientations_are_preserved(self):
        for text in ("图1", "表1"):
            for rotate in (0,90):
                with self.subTest(text=text,rotate=rotate):
                    if self.path.exists():self.path.unlink()
                    doc=self.document(text=text,gray=.87,fontsize=12,position=(300,650),rotate=rotate)
                    self.assertTrue(research_document(doc).pages[1].unreadable)
