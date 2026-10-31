"""The publication gate must verify the exact program that produced the report."""
from copy import deepcopy
from pathlib import Path

from paper_compiler import programs
from paper_compiler.storage import write_json_atomic
from test_paper_compiler_compiler import fixture
from test_paper_compiler_programs import candidate
from test_paper_compiler_publication_entry import entry, fake_review


def test_cli_reviews_the_rebound_program_from_a_legacy_package(tmp_path, monkeypatch):
    module = entry('paper_compiler_cli.py')
    ir, _ = fixture(tmp_path)
    source = tmp_path / 'ir.json'
    write_json_atomic(source, ir)
    legacy = deepcopy(programs.REGISTRY)
    legacy['capabilities']['external_work']['version'] = 'legacy-external-work/0'
    with monkeypatch.context() as old:
        old.setattr(programs, 'REGISTRY', legacy)
        package = programs.build_program({**candidate(), 'rule_id': '31'},
            rule_text='The entry must be Hello', basis=[{'id': 'test', 'text': 'The entry must be Hello'}])
    directory = tmp_path / 'legacy-package'
    programs.save_program(package, directory)
    calls = fake_review(monkeypatch)
    args = module.parser().parse_args(['check', '--ir', str(source), '--package', str(directory),
        '--out', str(tmp_path / 'report.json'), '--offline', '--publication-review',
        '--cache', str(tmp_path / 'cache'), '--ledger', str(tmp_path / 'ledger')])
    module.execute(args)
    report, reviewed = calls[0][2], calls[0][3]
    actual_version = report['rules'][0]['program_version']
    assert actual_version != package['manifest']['version_id']
    assert reviewed[0]['manifest']['version_id'] == actual_version
