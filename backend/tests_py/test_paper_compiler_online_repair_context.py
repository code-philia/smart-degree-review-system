import json

import paper_compiler.online_loop as online
from paper_compiler.runtime_control import RuntimeControl
from test_paper_compiler_online_loop import FIX, call, mutant, package
from test_paper_compiler_repair_history import OnlineClient


def test_actual_analysis_limitations_reach_repair_without_private_report_leak(tmp_path, monkeypatch):
    original_detect = online.detect

    def detect(*args, **kwargs):
        ir, analysis, report = original_detect(*args, **kwargs)
        analysis['coverage']['p'] = {'status': 'partial', 'reason': 'source evidence is incomplete'}
        return ir, analysis, report

    monkeypatch.setattr(online, 'detect', detect)
    client = OnlineClient([FIX])
    result = call(tmp_path, mutant(tmp_path), [package()], client, RuntimeControl(tmp_path / 'control'))
    feedback = client.inputs[0]['feedback']
    context = next(row['analysis_context'] for row in feedback if row.get('node_id') == 'p')
    assert context['coverage']['p'] == {'status': 'partial', 'reason': 'source evidence is incomplete'}
    assert context['ir_coverage'] == result['ir']['coverage']
    assert result['runtime']['status'] == 'promoted'
    assert '_feedback_context' not in json.dumps(result['report'])
    for path in (tmp_path / 'online').rglob('report.json'):
        assert '_feedback_context' not in path.read_text()
