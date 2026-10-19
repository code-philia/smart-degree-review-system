"""Frequency summaries over caller-admitted feedback, without detector calls."""
from copy import deepcopy
import pytest
from paper_compiler import repair_feedback as feedback


def examples():
    return [
        {'id':'one','before':'PASS','after':'VIOLATION','expected':'VIOLATION','failure_types':['difference'],
         'actual_original':[{'check_id':'local','status':'PASS'}],
         'actual_mutant':[{'check_id':'fallback','status':'UNKNOWN'}]},
        {'id':'two','before':'UNKNOWN','after':'UNKNOWN','expected':'VIOLATION','failure_types':['difference'],
         'actual_original':[{'check_id':'fallback','status':'UNKNOWN'},{'check_id':'local','status':'PASS'}],
         'actual_mutant':[{'check_id':'fallback','status':'UNKNOWN'}]},
        {'id':'three','before':'UNKNOWN','after':'VIOLATION','expected':'PASS','failure_types':['difference'],
         'actual_original':[{'check_id':'fallback','status':'UNKNOWN'}],
         'actual_mutant':[{'check_id':'edge:status','status':'VIOLATION'},{'check_id':'local','status':'VIOLATION'},{'check_id':'local','status':'VIOLATION'}]},
        {'failure_types':['compile_or_contract'],'reason':'Synthetic compile failure'},
    ]


def test_before_after_counts_cover_all_admitted_rows_not_only_selected_example():
    packet=feedback.prepare_feedback(examples(),limit=1)
    assert len(packet['feedback'])==1
    assert packet['feedback_summary']['before_statuses']=={'PASS':1,'UNKNOWN':2}
    assert packet['feedback_summary']['after_statuses']=={'UNKNOWN':1,'VIOLATION':2}


def test_diagnostic_counts_keep_sides_pairs_and_repeated_raw_occurrences_separate():
    summary=feedback.prepare_feedback(examples(),limit=1)['feedback_summary']
    assert summary['diagnostic_counts']=={
        'actual_original':[{'check_id':'fallback','status':'UNKNOWN','count':2},
                           {'check_id':'local','status':'PASS','count':2}],
        'actual_mutant':[{'check_id':'fallback','status':'UNKNOWN','count':2},
                         {'check_id':'local','status':'VIOLATION','count':2},
                         {'check_id':'edge:status','status':'VIOLATION','count':1}],
    }


def test_diagnostic_pair_order_is_stable_when_feedback_and_diagnostic_order_change():
    rows=examples();reordered=deepcopy(list(reversed(rows)))
    for row in reordered:
        for side in ['actual_original','actual_mutant']:row[side]=list(reversed(row.get(side,[])))
    assert feedback.prepare_feedback(rows)['feedback_summary']['diagnostic_counts']==feedback.prepare_feedback(reordered)['feedback_summary']['diagnostic_counts']


def test_missing_check_id_is_preserved_as_null_instead_of_inventing_a_check():
    summary=feedback.prepare_feedback([{'actual_original':[{'status':'ERROR'}]}])['feedback_summary']
    assert summary['diagnostic_counts']['actual_original']==[{'check_id':None,'status':'ERROR','count':1}]
    assert summary['diagnostic_counts']['actual_mutant']==[]


def test_empty_and_compile_only_feedback_do_not_invent_statuses_or_diagnostics():
    for rows in [[],[{'failure_types':['compile_or_contract'],'reason':'Synthetic'}]]:
        summary=feedback.prepare_feedback(rows)['feedback_summary']
        assert summary['before_statuses']==summary['after_statuses']=={}
        assert summary['diagnostic_counts']=={'actual_original':[],'actual_mutant':[]}


def test_summary_does_not_modify_feedback_source_labels_states_or_roundtrip():
    rows=examples();rows[0]['label_evidence']={'quotes':[{'quote':'Exact normative source'}]}
    before=deepcopy(rows);packet=feedback.prepare_feedback(rows,limit=12)
    assert rows==before
    assert feedback.restore_feedback(packet)==before
    assert packet['feedback_summary']['total_failures']==4
    assert packet['feedback_summary']['expected_statuses']=={'PASS':1,'VIOLATION':2}


def test_real_repair_request_carries_raw_frequency_summary_and_generic_code_tracing_hint(tmp_path):
    from paper_compiler import synthesis
    class Capture:
        def complete_json(self,task,instructions,data,max_tokens):
            self.instructions,self.data=instructions,deepcopy(data)
            return {'rule_id':data['requested_rule_id'],'title':'Synthetic source rule',
                    'requires':[],'target_kinds':['Paragraph'],'analysis_requests':[],
                    'model_patch':{},'code':'def detect(payload):\n    return []\n'}
    client=Capture()
    synthesis.synthesize_program({'rule_id':'synthetic-frequency','rule_text':'A generic source rule.','basis':[]},client,tmp_path,
        feedback=examples(),repair_context={'attempt':1,'history':[]})
    assert client.data['feedback_summary']['before_statuses']=={'PASS':1,'UNKNOWN':2}
    assert 'side-specific diagnostic_counts' in client.instructions
    assert 'trace frequent observed outcomes back to previous_candidate.code' in client.instructions
