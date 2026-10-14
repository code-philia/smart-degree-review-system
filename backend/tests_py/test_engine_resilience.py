"""A slow or failed full parse must not starve subsequent text recovery."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf
from pdf_rules.engine import detect
from pdf_rules.mineru_api import MinerUError
from pdf_rules.mineru_layout import LayoutObject

class EngineResilienceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'paper.pdf'
        with pymupdf.open() as bitmap:
            p=bitmap.new_page(width=240,height=160);p.draw_rect((0,0,240,160),fill=(.3,.5,.7))
            png=p.get_pixmap().tobytes('png')
        with pymupdf.open() as pdf:
            pdf.new_page(width=600,height=800).insert_image((30,50,570,750),stream=png,keep_proportion=False)
            pdf.save(self.path)
        self.title=LayoutObject('text',1,(60,70,540,90),'Experimental Results',600,800,'title')
        text=['正文如图8.2所示。']+['本章介绍实验数据的采集方法和处理过程，并对不同实验条件下的结果开展分析。']*4
        self.body=[]
        for i,t in enumerate(text):
            box=(60,100+i*130,540,130+i*130)
            self.body.append(LayoutObject('text',1,box,t,600,800,'text',((t,box),)))
    def test_full_parse_reserves_time_for_ocr_and_cpu_recovery(self):
        with patch('pdf_rules.engine.parse_layout',return_value=[self.title]) as cloud,patch('pdf_rules.engine._ocr_missing_pages',return_value=self.body):
            output=detect(self.path,[11,13],token='fixture-token')
        self.assertLessEqual(cloud.call_args.kwargs['max_seconds'],420)
        self.assertEqual(output['rules']['11']['status'],'completed')
        self.assertEqual([f['token'] for f in output['rules']['11']['findings']],['8.2'])
    def test_temporary_full_layout_failure_automatically_resumes_before_giving_up(self):
        full=[self.title,*self.body]
        with patch('pdf_rules.engine.parse_layout',side_effect=[MinerUError('MinerU network request failed',retryable=True),full]) as parser:
            output=detect(self.path,[11,13],token='fixture-token')
        self.assertEqual(parser.call_count,2)
        self.assertEqual(output['rules']['11']['status'],'completed')
        self.assertEqual(output['rules']['13']['status'],'completed')
        self.assertEqual([f['token'] for f in output['rules']['11']['findings']],['8.2'])

    def test_failed_full_layout_does_not_skip_local_ocr_recovery(self):
        with patch('pdf_rules.engine.parse_layout',side_effect=MinerUError('MinerU task timed out',retryable=True)),patch('pdf_rules.engine._ocr_missing_pages',return_value=self.body):
            output=detect(self.path,[11,13],token='fixture-token')
        self.assertEqual(output['rules']['11']['status'],'completed')
        self.assertEqual([f['token'] for f in output['rules']['11']['findings']],['8.2'])
        self.assertEqual(output['rules']['13']['status'],'unsupported')
    def test_failed_forced_ocr_does_not_skip_remaining_grid_recovery(self):
        def recovery(*args,**kwargs):
            if not kwargs.get('tiled'):raise MinerUError('MinerU network request failed',retryable=True)
            return self.body
        with patch('pdf_rules.engine.parse_layout',return_value=[self.title]),patch('pdf_rules.engine._ocr_missing_pages',side_effect=recovery) as parser:
            output=detect(self.path,[11,13],token='fixture-token')
        self.assertEqual(output['rules']['11']['status'],'completed')
        self.assertTrue(any(c.kwargs.get('tiled')=='grid' for c in parser.call_args_list))

if __name__=='__main__':unittest.main()
