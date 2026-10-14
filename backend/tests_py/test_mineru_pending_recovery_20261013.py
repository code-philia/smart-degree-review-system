"""Pending tasks retain their batch and completed downloads use the hard budget."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from pdf_rules.mineru_api import MinerUError, parse_layout
from pdf_rules.mineru_cache import RawLayoutCache, TaskState
from test_mineru_api import FakeHttp, fake_zip


class Clock:
    value = 0

    def monotonic(self):
        return self.value

    def sleep(self, delay):
        self.value += delay


class PendingRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'paper.pdf'
        self.cache = RawLayoutCache(Path(folder.name) / 'cache')
        with pymupdf.open() as pdf:
            for _ in range(4):
                pdf.new_page(width=600, height=800)
            pdf.save(self.path)

    def run_parse(self, http, clock, **options):
        with patch.dict(os.environ, {'MINERU_CACHE_DIR': str(self.cache.folder)}), \
                patch('pdf_rules.mineru_api.time.monotonic', clock.monotonic), \
                patch('pdf_rules.mineru_api.time.sleep', clock.sleep):
            return parse_layout(self.path, 'fixture-token', http, **options)

    def test_done_result_download_uses_total_budget_without_resubmission(self):
        clock = Clock()

        class SlowDoneHttp(FakeHttp):
            def request(self, method, url, **kwargs):
                if '/extract-results/' in url and clock.value < 174:
                    return {'code': 0, 'data': {'extract_result': [{'state': 'running'}]}}
                if 'download.test' in url:
                    remaining = kwargs['timeout']
                    if remaining < 15:
                        clock.value += remaining
                        raise OSError('download still in progress')
                    clock.value += 15
                return super().request(method, url, **kwargs)

        http = SlowDoneHttp(lambda count: fake_zip(page_count=count))
        objects = self.run_parse(http, clock, max_seconds=240)
        self.assertEqual([o.page_number for o in objects if o.kind == 'figure'], [1])
        self.assertEqual(sum(call[0] == 'POST' for call in http.calls), 1)
        self.assertLess(clock.value, 240)

    def test_existing_pending_task_is_polled_past_split_watchdog_without_new_upload(self):
        state = TaskState(self.cache, self.cache.key(self.path.read_bytes()), 'fixture-token')
        state.write('retained-batch')
        clock = Clock()

        class CompletingHttp(FakeHttp):
            chunk_pages = 4

            def request(self, method, url, **kwargs):
                if '/extract-results/' in url and clock.value < 190:
                    return {'code': 0, 'data': {'extract_result': [{'state': 'running'}]}}
                return super().request(method, url, **kwargs)

        http = CompletingHttp(lambda count: fake_zip(page_count=count))
        objects = self.run_parse(http, clock, max_seconds=240)
        self.assertEqual([o.page_number for o in objects if o.kind == 'figure'], [1])
        self.assertFalse(any(call[0] in {'POST', 'PUT'} for call in http.calls))
        self.assertIsNone(state.read())

    def test_existing_running_task_keeps_hard_timeout_and_pending_identity(self):
        state = TaskState(self.cache, self.cache.key(self.path.read_bytes()), 'fixture-token')
        state.write('retained-batch')
        clock = Clock()

        class RunningHttp(FakeHttp):
            def request(self, method, url, **kwargs):
                if '/extract-results/' in url:
                    self.calls.append((method, url, {}, None))
                    return {'code': 0, 'data': {'extract_result': [{'state': 'running'}]}}
                return super().request(method, url, **kwargs)

        http = RunningHttp()
        with self.assertRaises(MinerUError):
            self.run_parse(http, clock, max_seconds=200)
        self.assertEqual(clock.value, 200)
        self.assertEqual(state.read(), 'retained-batch')
        self.assertFalse(any(call[0] in {'POST', 'PUT'} for call in http.calls))


if __name__ == '__main__':
    unittest.main()
