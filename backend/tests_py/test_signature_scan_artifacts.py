"""Regression cases for administrative scan artifacts, not research content."""
from dataclasses import replace
import random
import unittest
import pymupdf
import test_signature_page_content as fixtures
from pdf_rules.model import PdfDocument, PdfLine
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.signature_ocr import recover_signature_pages, recovery_regions as signature_regions

class SignatureScanArtifactTests(unittest.TestCase):
    def document(self, *, barcode=False, border=False, noise=False, text=None, fontsize=12, crease=False):
        fixture=fixtures.SignaturePageContentTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        doc=fixture.document()
        image=pymupdf.open();page=image.new_page(width=600,height=800)
        page.draw_rect(page.rect,fill=(.994,)*3,color=None)
        page.insert_text((60,100),'Committee signature table',fontsize=12)
        if border:page.draw_rect((58,78,542,278),color=(.3,)*3,width=.6)
        if barcode:
            for i in range(24):
                x=430+i*2;page.draw_rect((x,12,x+.6+(i%3)*.3,32),fill=(.1,)*3,color=None)
            page.insert_text((430,40),'123456789012',fontsize=6)
        if noise:
            rng=random.Random(1907)
            for _ in range(80):
                x=rng.uniform(25,565);y=rng.uniform(350,750)
                page.draw_circle((x,y),rng.uniform(.3,1.2),fill=(rng.uniform(.94,.995),)*3,color=None)
        if crease:page.draw_rect((560,98,563,108),fill=(.99,)*3,color=None)
        if text:page.insert_text((60,650),text,fontsize=fontsize,fontname='china-s',color=(.99,)*3)
        png=page.get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png');image.close()
        doc.path.unlink()
        pdf=pymupdf.open();pdf.new_page(width=600,height=800)
        pdf.new_page(width=600,height=800).insert_image((0,0,600,800),stream=png)
        pdf.save(doc.path);pdf.close()
        page=replace(extract_pdf(doc.path).pages[1],lines=doc.pages[1].lines)
        return PdfDocument(doc.path,(doc.pages[0],page))

    def test_barcode_on_verified_signature_page_does_not_block_local_rules(self):
        doc=self.document(barcode=True)
        recovered,evidence=recover_signature_pages(doc,{2})
        self.assertFalse(recovered.pages[1].unreadable,evidence)

    def test_known_table_border_and_sparse_scan_speckles_are_not_unread_text(self):
        doc=self.document(border=True,noise=True)
        recovered,evidence=recover_signature_pages(doc,{2})
        self.assertFalse(recovered.pages[1].unreadable,evidence)

    def test_tiny_faint_reference_with_scan_noise_is_still_input_or_unread(self):
        doc=self.document(noise=True,text='详见附录Z。',fontsize=4)
        recovered,evidence=recover_signature_pages(doc,{2})
        self.assertTrue(recovered.pages[1].unreadable or any('附录Z' in line.text for line in recovered.pages[1].lines),evidence)

    def test_committee_roster_can_continue_without_repeated_column_headings(self):
        doc=self.document()
        previous=replace(doc.pages[0],lines=(replace(doc.pages[0].lines[0],text=doc.pages[0].lines[0].text+' '+fixtures.FIELDS),))
        page=replace(doc.pages[1],lines=(replace(doc.pages[1].lines[0],text='委员 张三 教授 计算机学院 委员 李四 教授 计算机学院 秘书 王五 计算机学院'),))
        self.assertTrue(signature_regions(previous,page))

    def test_native_form_fields_can_establish_signature_continuation_context(self):
        doc=self.document()
        previous=replace(doc.pages[0],lines=(PdfLine(1,'上海交通大学博士学位论文答辩决议书',(60,60,540,80),600,800,source='native'),
            PdfLine(1,'姓名 学号 所在学科 指导教师 答辩日期 答辩地点 论文题目 评语和决议 投票表决结果 答辩结论 经答辩委员会讨论 同意通过博士学位论文答辩 建议授予博士学位',(60,100,540,700),600,800,source='native')))
        self.assertTrue(signature_regions(previous,doc.pages[1]))

    def test_secretary_row_without_preceding_complete_roster_is_not_enough(self):
        doc=self.document()
        page=replace(doc.pages[1],lines=(replace(doc.pages[1].lines[0],text='秘书 王五 计算机学院'),))
        self.assertEqual(signature_regions(doc.pages[0],page),[])

    def test_formal_verdict_and_chair_signature_continue_verified_form(self):
        doc=self.document()
        page=replace(doc.pages[1],lines=(replace(doc.pages[1].lines[0],text='投票表决结果 同意票数 实到委员数 应到委员数 答辩结论 通过 建议授予硕士学位 答辩委员会主席（签字） 2026年1月9日',bbox=(60,340,540,460)),))
        self.assertTrue(signature_regions(doc.pages[0],page))

    def test_rotated_roster_continuation_uses_display_coordinates(self):
        doc=self.document()
        previous=replace(doc.pages[0],width=800,height=600,display_rotation=90,lines=(replace(doc.pages[0].lines[0],text=doc.pages[0].lines[0].text+' '+fixtures.FIELDS),))
        page=replace(doc.pages[1],width=800,height=600,display_rotation=90,lines=(replace(doc.pages[1].lines[0],text='委员 张三 教授 计算机学院 秘书 王五 计算机学院',bbox=(60,60,230,540)),))
        self.assertTrue(signature_regions(previous,page))

    def test_thin_low_contrast_scan_crease_is_not_an_unread_text_line(self):
        doc=self.document(crease=True)
        recovered,evidence=recover_signature_pages(doc,{2})
        self.assertFalse(recovered.pages[1].unreadable,evidence)

    def test_tiny_short_references_are_not_accepted_as_clean_paper(self):
        for text in ('图1','表1','附录Z'):
            with self.subTest(text=text):
                doc=self.document(text=text,fontsize=4)
                recovered,evidence=recover_signature_pages(doc,{2})
                self.assertTrue(recovered.pages[1].unreadable or any(text in line.text for line in recovered.pages[1].lines),evidence)
