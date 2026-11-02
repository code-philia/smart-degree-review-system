import pymupdf
import pytest

from paper_compiler.frontend import build_paper
from paper_compiler.llm import ModelError


class UnavailableSelector:
    calls = 0

    def complete_json(self, *args):
        self.calls += 1
        raise ModelError('paid_or_interrupted_input_without_success_cache')


def make_pdf(tmp_path, *, ambiguous=False, weak=False):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((60, 80), 'Contents', fontsize=18)
    page.insert_text((60, 120), 'References', fontsize=12)
    page.insert_text((60, 150), '1 Introduction', fontsize=12)
    for _ in range(2 if ambiguous else 1):
        page = document.new_page()
        page.insert_text((60, 35), 'References', fontsize=9)
        page.insert_text((60, 100), 'References', fontsize=12 if weak else 18)
        for index in range(1, 4):
            page.insert_text((60, 130 + index * 35),
                             f'[{index}] Smith A. A genuine research title[J]. Journal, 202{index}.', fontsize=12)
    path = tmp_path / 'bibliography.pdf'
    document.save(path)
    document.close()
    return path


def test_unavailable_selector_recovers_one_source_corroborated_bibliography(tmp_path):
    model = UnavailableSelector()
    ir = build_paper(make_pdf(tmp_path), client=model)
    entries = [node for node in ir['nodes'] if node['kind'] == 'BibliographyEntry']
    assert [node['attrs']['key'] for node in entries] == ['1', '2', '3']
    assert model.calls == 1
    assert ir['metadata']['bibliography_selection'] == 'source_corroborated_after_model_error'
    assert ir['metadata']['bibliography_observations'][0]['status'] == 'unavailable'
    assert ir['coverage']['bibliography']['status'] == 'partial'
    assert all(node['provenance'] for node in entries)


@pytest.mark.parametrize('options', [{'ambiguous': True}, {'weak': True}])
def test_unavailable_selector_keeps_ambiguous_or_weak_bibliography_unlocated(tmp_path, options):
    ir = build_paper(make_pdf(tmp_path, **options), client=UnavailableSelector())
    assert not [node for node in ir['nodes'] if node['kind'] == 'BibliographyEntry']
    assert ir['metadata']['bibliography_selection'] == 'model_error_unlocated'
    assert ir['coverage']['bibliography']['status'] == 'partial'
