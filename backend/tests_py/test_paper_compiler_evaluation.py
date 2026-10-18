import pytest
from paper_compiler.evaluation import score_pair,summarize_pairs


def report(status,node='entry',check='format'):
    return {'rules':[{'rule_id':'31','results':[{'node_id':node,'check_id':check,'status':status}]}]}

def oracle(parent='p1'):
    return {'rule_id':'31','target_node_id':'entry','target_check_id':'format','status':'VIOLATION','parent_sha256':parent,'evidence_domain':'source_format','valid':True}


def test_existing_elsewhere_violation_is_not_mutation_detection():
    result=score_pair(oracle(),report('PASS'),report('VIOLATION',node='elsewhere'))
    assert result['outcome']=='unlocalizable'


def test_existing_target_violation_excludes_the_pair():
    result=score_pair(oracle(),report('VIOLATION'),report('VIOLATION'))
    assert result['outcome']=='invalid_parent' and not result['valid_pair']


def test_unknowns_remain_in_denominator_not_true_negatives():
    result=score_pair(oracle(),report('PASS'),report('UNKNOWN'))
    assert result['outcome']=='undecidable' and not result['detected']
    summary=summarize_pairs([result]);assert summary['by_rule']['31']['undecidable']==1


def test_duplicate_parents_and_synthetic_domains_do_not_fill_real_parent_target():
    records=[score_pair(oracle(),report('PASS'),report('VIOLATION')) for _ in range(3)]
    other=oracle('p2');other['evidence_domain']='controlled_catalogue'
    records.append(score_pair(other,report('PASS'),report('VIOLATION')))
    summary=summarize_pairs(records)
    assert summary['by_rule']['31']['distinct_real_parents']==1
    assert summary['by_rule']['31']['target_shortfall']==99


def test_exact_target_detection_is_recorded():
    result=score_pair(oracle(),report('PASS'),report('VIOLATION'))
    assert result['detected'] and result['valid_pair']
