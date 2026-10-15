"""A signature scan must be read, rather than having its pixels discarded."""
import unittest
from unittest.mock import patch
from pdf_rules.engine import detect
from pdf_rules.mineru_layout import LayoutObject
import test_signature_page_content as fixtures

class SignatureOcrIntegrationTests(unittest.TestCase):
    def document(self, **kwargs):
        fixture=fixtures.SignaturePageContentTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture.document(**kwargs)

    def detect_document(self, doc, rule=29):
        line=doc.pages[1].lines[0]
        objects=[LayoutObject("text",2,l.bbox,l.text,600,800,"table_body") for l in doc.pages[1].lines]
        with patch("pdf_rules.engine.extract_pdf",return_value=doc), patch("pdf_rules.engine._ocr_missing_pages",return_value=objects):
            return detect(doc.path,[rule],token="fixture")["rules"][str(rule)]

    def test_complete_signature_with_no_other_text_finishes(self):
        result=self.detect_document(self.document())
        self.assertEqual(result["status"],"completed")
        self.assertEqual(result["findings"],[])

    def test_faint_appendix_reference_below_signature_is_read_and_reported(self):
        result=self.detect_document(self.document(text="详见附录Z。",gray=.99,fontsize=12))
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])
        self.assertEqual(result["findings"][0]["page"],2)
        self.assertGreater(result["findings"][0]["location"]["bounding_rect"]["y1"],600)

    def test_short_figure_reference_is_not_removed_as_noise(self):
        result=self.detect_document(self.document(text="如图1所示",gray=.87,fontsize=12),rule=11)
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["1"])

    def test_rotated_reference_is_read(self):
        result=self.detect_document(self.document(text="详见附录Z。",gray=.87,fontsize=12,
                                                  position=(300,650),rotate=90))
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])

    def test_unread_tiny_faint_reference_cannot_become_a_clean_result(self):
        result=self.detect_document(self.document(text="详见附录Z。",gray=.99,fontsize=4))
        self.assertTrue(result["status"]!="completed" or any(f["token"]=="Z" for f in result["findings"]))

    def test_model_failure_does_not_become_a_clean_result(self):
        import cv2
        from rapidocr.inference_engine.onnxruntime import ONNXRuntimeError
        for failure in (RuntimeError,ONNXRuntimeError,cv2.error):
            with self.subTest(exception=failure.__name__), patch("pdf_rules.signature_ocr.read_remainder",side_effect=failure("fixture inference error")):
                self.assertEqual(self.detect_document(self.document())["status"],"unsupported")

    def test_ordinary_unread_scan_does_not_use_signature_recovery(self):
        from dataclasses import replace
        from pdf_rules.model import PdfDocument,PdfLine
        doc=self.document()
        first=replace(doc.pages[0],lines=(PdfLine(1,"第一章 正文",(60,80,540,100),600,800),))
        doc=PdfDocument(doc.path,(first,doc.pages[1]))
        with patch("pdf_rules.signature_ocr.read_remainder") as reader:
            self.assertEqual(self.detect_document(doc)["status"],"unsupported")
            reader.assert_not_called()

    def test_appendix_reference_in_footer_is_read(self):
        result=self.detect_document(self.document(text="详见附录Z。",gray=.87,fontsize=12,
                                                  position=(60,790)))
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])

    def test_shorter_high_confidence_read_cannot_replace_full_reference(self):
        import numpy as np
        from time import monotonic
        from pdf_rules.local_ocr import OcrText,read_remainder,has_unread_text
        gray=np.indices((390,390)).sum(axis=0)%2+252
        full=OcrText("详见附录Z。",.90,(30,30,100,50))
        prefix=OcrText("详见",.99,(30,30,60,50))
        with patch("pdf_rules.local_ocr._read_tile",side_effect=[[full],[prefix],[],[],[],[],[],[]]):
            hits,_=read_remainder(gray.astype("uint8"),3,deadline=monotonic()+10)
        self.assertTrue(any("附录Z" in h.text for h in hits))
        self.assertFalse(has_unread_text(hits))

    def test_nonempty_low_confidence_read_is_retained_as_model_output(self):
        from pdf_rules.local_ocr import OcrText,has_unread_text
        self.assertFalse(has_unread_text([OcrText("1",.1,(0,0,10,10))]))
        self.assertTrue(has_unread_text([OcrText("",0,(0,0,10,10),.95)]))

    def test_reference_in_separate_footer_image_is_not_masked(self):
        import pymupdf
        from dataclasses import replace
        from pdf_rules.model import PdfDocument
        from pdf_rules.pdf_extract import extract_pdf
        doc=self.document()
        with pymupdf.open() as image_pdf:
            p=image_pdf.new_page(width=150,height=30)
            p.insert_text((2,22),"详见附录Z。",fontsize=12,fontname="china-s",color=(.87,)*3)
            png=p.get_pixmap(matrix=pymupdf.Matrix(3,3)).tobytes("png")
        with pymupdf.open(doc.path) as source:
            source[1].insert_image((60,760,210,790),stream=png)
            source.saveIncr()
        page=extract_pdf(doc.path).pages[1]
        doc=PdfDocument(doc.path,(doc.pages[0],replace(page,lines=doc.pages[1].lines)))
        result=self.detect_document(doc)
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])

    def test_low_confidence_reference_still_reaches_rule_detection(self):
        from pdf_rules.local_ocr import OcrText
        doc=self.document()
        line=doc.pages[1].lines[0]
        objects=[LayoutObject("text",2,l.bbox,l.text,600,800,"table_body") for l in doc.pages[1].lines]
        weak=OcrText("详见附录Z。",.3,(60,600,180,620),.6)
        with patch("pdf_rules.engine.extract_pdf",return_value=doc), patch("pdf_rules.engine._ocr_missing_pages",return_value=objects), patch("pdf_rules.signature_ocr.read_remainder",return_value=([weak],1)):
            output=detect(doc.path,[29],token="fixture")
        result=output["rules"]["29"]
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])
        self.assertEqual(output["parse_recovery"][0]["quality"],"low_confidence")

    def test_overlapping_ocr_table_tiles_form_one_signature_table(self):
        from dataclasses import replace
        from pdf_rules.model import PdfDocument,PdfLine
        doc=self.document(text="详见附录Z。",gray=.87,fontsize=12)
        fragments=(PdfLine(2,"答辩委员会工作职务 姓名 主席 委员 委员 委员 秘书",(60,80,330,275),600,800,source="mineru",role="table_body"),
                   PdfLine(2,"职称 工作单位 签名",(250,80,540,275),600,800,source="mineru",role="table_body"))
        doc=PdfDocument(doc.path,(doc.pages[0],replace(doc.pages[1],lines=fragments)))
        result=self.detect_document(doc)
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])

    def test_text_in_gap_between_overlapping_table_tiles_is_not_masked(self):
        from dataclasses import replace
        from pdf_rules.model import PdfDocument,PdfLine
        doc=self.document(text="详见附录Z。",gray=.87,fontsize=12,position=(60,340))
        fragments=(PdfLine(2,"答辩委员会工作职务 姓名 主席 委员 委员 委员 秘书",(60,80,330,275),600,800,source="mineru",role="table_body"),
                   PdfLine(2,"职称 工作单位 签名",(250,200,540,380),600,800,source="mineru",role="table_body"))
        doc=PdfDocument(doc.path,(doc.pages[0],replace(doc.pages[1],lines=fragments)))
        result=self.detect_document(doc)
        self.assertEqual(result["status"],"completed")
        self.assertEqual([item["token"] for item in result["findings"]],["Z"])
