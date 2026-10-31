"""Independent campus extraction overlaps without changing grounded analysis."""
import copy
import threading
import time

import pytest

from paper_compiler import analysis
from paper_compiler.budget import BudgetExceeded
from paper_compiler.contracts import validate_analysis
from paper_compiler.llm import ModelError
from test_paper_compiler_bibliography_batch import Fields, paper


def test_campus_batches_overlap_and_merge_identically_to_serial(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '8')
    ir = paper(tmp_path, 65)
    original = copy.deepcopy(ir)
    barrier = threading.Barrier(8, timeout=2)
    lock = threading.Lock()

    class CampusFields(Fields):
        config = {'MODEL_PROVIDER': 'sjtu'}
        active = peak = 0

        def complete_json(self, *args):
            first = int(args[2]['entries'][0]['id'][1:])
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                if first < 64:
                    barrier.wait()
                    time.sleep((64 - first) / 1000)
                return super().complete_json(*args)
            finally:
                with lock:
                    self.active -= 1

    client = CampusFields()
    parallel = analysis.base_analysis(ir)
    analysis.parse_entries(ir, parallel, client)
    serial = analysis.base_analysis(ir)
    analysis.parse_entries(ir, serial, Fields())
    assert client.peak == 8
    assert parallel == serial
    assert ir == original
    validate_analysis(ir, parallel)


def test_model_error_is_scoped_to_its_own_campus_batch(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '8')
    ir = paper(tmp_path, 17)

    class CampusFields(Fields):
        config = {'MODEL_PROVIDER': 'sjtu'}

        def complete_json(self, *args):
            if args[2]['entries'][0]['id'] == 'e8':
                raise ModelError('temporary provider failure')
            return super().complete_json(*args)

    result = analysis.base_analysis(ir)
    analysis.parse_entries(ir, result, CampusFields())
    facts = result['results']['bibliography_fields']
    assert facts['e0']['title']['value'] == 'Title 00'
    assert facts['e16']['title']['value'] == 'Title 16'
    for index in range(8, 16):
        assert facts[f'e{index}']['title']['state'] == 'unknown'
        assert 'ModelError' in facts[f'e{index}']['title']['reason']
    validate_analysis(ir, result)


def test_fatal_error_stops_scheduling_new_campus_batches(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '8')
    ir = paper(tmp_path, 160)
    lock = threading.Lock()

    class CampusFields(Fields):
        config = {'MODEL_PROVIDER': 'sjtu'}

        def complete_json(self, *args):
            first = args[2]['entries'][0]['id']
            with lock:
                self.started.append(first)
            if first == 'e8':
                raise BudgetExceeded('task deadline exhausted')
            time.sleep(.03)
            return super().complete_json(*args)

    client = CampusFields()
    client.started = []
    result = analysis.base_analysis(ir)
    with pytest.raises(BudgetExceeded, match='deadline'):
        analysis.parse_entries(ir, result, client)
    assert len(client.started) <= 9
    assert list(result['results']['bibliography_fields']) == [f'e{i}' for i in range(8)]
