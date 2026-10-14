"""Consumer-visible safe diagnostics across the real engine error boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from pdf_rules.engine import detect
from pdf_rules.mineru_api import MinerUError
from pdf_rules.mineru_layout import LayoutObject


class EngineMinerUDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'paper.pdf'
        self.body = []
        for i, text in enumerate(['正文如图8.2所示。'] + [
            '本章介绍实验数据的采集方法和处理过程，并对不同实验条件下的结果开展分析。'] * 4):
            box = (60, 100 + i * 130, 540, 130 + i * 130)
            self.body.append(LayoutObject('text', 1, box, text, 600, 800, 'text', ((text, box),)))
        self.title = LayoutObject('text', 1, (60, 70, 540, 90),
                                  'Experimental Results', 600, 800, 'title')
        self.safe = {'operation': 'PUT', 'attempts': 4, 'exception_type': 'URLError',
                     'reason_type': 'ConnectionResetError', 'errno': 104,
                     'transport_mode': 'direct'}

    def paper(self, scanned=False, rotated=False):
        with pymupdf.open() as doc:
            page = doc.new_page(width=600, height=800)
            if scanned:
                with pymupdf.open() as raster:
                    image = raster.new_page(width=240, height=160)
                    image.draw_rect((0, 0, 240, 160), fill=(.3, .5, .7))
                    png = image.get_pixmap().tobytes('png')
                page.insert_image((30, 50, 570, 750), stream=png, keep_proportion=False)
            else:
                page.insert_text((40, 60), 'Experimental Results and research data.')
            if rotated:
                page.set_rotation(90)
            doc.save(self.path)

    def test_final_cloud_failure_retains_safe_diagnostics_and_rejects_private_fields(self):
        self.paper()
        supplied = {**self.safe, 'url': 'https://private.invalid/secret',
                    'token': 'secret-token', 'headers': {'Authorization': 'secret-token'},
                    'response': 'secret-response', 'batch_id': 'secret-batch'}
        error = MinerUError('MinerU network request failed', diagnostics=supplied)
        with patch('pdf_rules.engine.parse_layout', side_effect=error):
            result = detect(self.path, [13, 14], token='fixture-token')
        self.assertEqual(result['parse_attempts'][0]['diagnostics'], self.safe)
        for number in ('13', '14'):
            self.assertEqual(result['rules'][number],
                             {'status': 'unsupported', 'reason': 'MinerU network request failed',
                              'findings': [], 'diagnostics': self.safe})
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(error.diagnostics, supplied)

    def test_final_failed_retry_uses_last_error_diagnostics(self):
        self.paper()
        last = {'operation': 'POST', 'attempts': 1, 'exception_type': 'HTTPError',
                'http_status': 401, 'transport_mode': 'direct'}
        errors = [MinerUError('MinerU network request failed', retryable=True, diagnostics=self.safe),
                  MinerUError('MinerU API rejected the request', diagnostics=last)]
        with patch('pdf_rules.engine.parse_layout', side_effect=errors):
            result = detect(self.path, [13], token='fixture-token')
        self.assertEqual([row['diagnostics'] for row in result['parse_attempts']], [self.safe, last])
        self.assertEqual(result['rules']['13']['diagnostics'], last)
        self.assertEqual(result['rules']['13']['status'], 'unsupported')

    def test_retry_success_keeps_failed_attempt_diagnostics_without_stale_rule_error(self):
        self.paper()
        failure = MinerUError('MinerU network request failed', retryable=True, diagnostics=self.safe)
        with patch('pdf_rules.engine.parse_layout', side_effect=[failure, [self.title, *self.body]]):
            result = detect(self.path, [13], token='fixture-token')
        self.assertEqual(result['parse_attempts'][0]['diagnostics'], self.safe)
        self.assertEqual(result['rules']['13']['status'], 'completed')
        self.assertNotIn('diagnostics', result['rules']['13'])
        self.assertNotIn('diagnostics', result['parse_attempts'][1])

    def test_independent_rotated_ocr_failures_keep_each_stage_diagnostics(self):
        self.paper(scanned=True, rotated=True)
        refused = {'operation': 'GET', 'attempts': 4, 'exception_type': 'URLError',
                   'reason_type': 'ConnectionRefusedError', 'errno': 111,
                   'transport_mode': 'direct'}
        def recover(*args, **kwargs):
            if kwargs.get('tiled') == 'grid':
                return self.body
            diagnostics = refused if kwargs.get('upright') else self.safe
            raise MinerUError('MinerU network request failed', retryable=True, diagnostics=diagnostics)
        with patch('pdf_rules.engine.parse_layout', return_value=[self.title]),                 patch('pdf_rules.engine._ocr_missing_pages', side_effect=recover):
            result = detect(self.path, [11, 13], token='fixture-token')
        attempts = {row['stage']: row for row in result['parse_attempts']}
        self.assertEqual(attempts['forced_ocr']['diagnostics'], self.safe)
        self.assertEqual(attempts['upright_ocr']['diagnostics'], refused)
        self.assertEqual(attempts['grid_ocr']['status'], 'completed')
        self.assertEqual(result['rules']['11']['status'], 'completed')

    def test_initial_local_ocr_failure_keeps_diagnostics_when_recovery_succeeds(self):
        self.paper(scanned=True)
        error = MinerUError('MinerU network request failed', diagnostics=self.safe)
        with patch('pdf_rules.engine._ocr_missing_pages', side_effect=[error, self.body]):
            result = detect(self.path, [11], token='fixture-token')
        self.assertEqual(result['parse_attempts'][0]['diagnostics'], self.safe)
        self.assertEqual(result['rules']['11']['status'], 'completed')

    def test_untrusted_values_are_dropped_without_creating_empty_diagnostics(self):
        self.paper()
        values = {'operation': 'https://private.invalid/secret',
                  'attempts': 'secret', 'exception_type': 'secret',
                  'reason_type': 'secret', 'errno': 'secret', 'http_status': True,
                  'transport_mode': 'secret', 'tls_reason': 'SECRET_TOKEN',
                  'timeout_phase':'https://private.invalid/secret'}
        with patch('pdf_rules.engine.parse_layout',
                   side_effect=MinerUError('MinerU network request failed', diagnostics=values)):
            result = detect(self.path, [13], token='fixture-token')
        self.assertNotIn('diagnostics', result['parse_attempts'][0])
        self.assertNotIn('diagnostics', result['rules']['13'])
        self.assertNotIn('secret', json.dumps(result).lower())

    def test_upload_slot_timeout_retains_only_the_known_safe_phase(self):
        self.paper()
        details = {'operation':'PUT', 'attempts':1, 'exception_type':'MinerUError',
                   'transport_mode':'direct', 'timeout_phase':'upload_slot'}
        with patch('pdf_rules.engine.parse_layout',
                   side_effect=MinerUError('MinerU task timed out', diagnostics=details)):
            result = detect(self.path, [13], token='fixture-token')
        self.assertEqual(result['parse_attempts'][0]['diagnostics'], details)
        self.assertEqual(result['rules']['13']['diagnostics'], details)

    def test_empty_optional_diagnostics_preserve_existing_record_shape(self):
        self.paper()
        with patch('pdf_rules.engine.parse_layout',
                   side_effect=MinerUError('MinerU API token is not configured')):
            result = detect(self.path, [13], token='fixture-token')
        self.assertEqual(result['parse_attempts'],
                         [{'stage': 'initial_layout', 'status': 'failed',
                           'reason': 'MinerU API token is not configured'}])
        self.assertEqual(result['rules']['13'],
                         {'status': 'unsupported', 'reason': 'MinerU API token is not configured',
                          'findings': []})


if __name__ == '__main__':
    unittest.main()
