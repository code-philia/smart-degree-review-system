from paper_compiler.pipeline import detect
from paper_compiler.fixed_r31 import build_r31_package
from paper_compiler.publication_gate import audit_positives
from test_paper_compiler_program_analysis import paper
from test_paper_compiler_fixed_r31 import SourceFacts


def test_verified_fixed_program_publishes_its_grounded_format_error_without_second_model_verdict(tmp_path):
    ir=paper(tmp_path);entry=next(n for n in ir['nodes'] if n['kind']=='BibliographyEntry')
    entry['text']='[1] A study[XX]. Journal, 2020.'
    entry['provenance']=[{'kind':'synthetic','operation_id':'format-test','ancestor_provenance':entry['provenance']}]
    client=SourceFacts({'title':'A study','type_code':'XX','year':'2020'})
    package=build_r31_package()
    ir,a,r=detect(ir,[package],client=client,gateway=None,cache_dir=tmp_path/'cache')
    result=audit_positives(ir,a,r,[package],client=client,gateway=None,output_dir=tmp_path/'published')
    assert result['public']['status']=='ALERT'
    assert result['public']['findings'][0]['node_id']=='entry'
    assert result['public']['findings'][0]['verification']=='fixed_program_and_grounded_facts'
    assert not result['internal']['proven_pass']
