"""Meter real ledger snapshots and executable loops; all external APIs are fake."""
import copy
from decimal import Decimal
import importlib
import importlib.util
import json
from pathlib import Path
import uuid

import pytest

from paper_compiler.analysis import base_analysis
from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.feedback_loop import run_feedback_loop
from paper_compiler.programs import build_program, check_programs
from test_paper_compiler_feedback_loop import ExternalModel, make_cases
from test_paper_compiler_programs import candidate
from test_paper_compiler_study import benchmark, Model as StudyModel, runner_for

TASK={'rule_id':'new-rule','rule_text':'Hello','basis':[{'id':'test','text':'Hello'}]}


def accounting():
    assert importlib.util.find_spec('paper_compiler.run_accounting') is not None, 'resource intervals are missing'
    return importlib.import_module('paper_compiler.run_accounting')


class Clock:
    def __init__(self):self.now=100.0
    def advance(self,seconds):self.now+=seconds


def clock(monkeypatch):
    value=Clock();monkeypatch.setattr(accounting(),'_monotonic',lambda:value.now);return value


def charge(ledger,amount='.1',*,uncertain=False,prompt=10,completion=5):
    rid=uuid.uuid4().hex;ledger.reserve(rid,amount,'framework-20261019','200')
    if uncertain:ledger.mark_uncertain(rid,'timeout')
    else:ledger.settle(rid,{'prompt_tokens':prompt,'completion_tokens':completion},amount)


class Metered(ExternalModel):
    def __init__(self,ledger,timer,*,bad_first=False,block=False):
        super().__init__();self.ledger=ledger;self.timer=timer;self.bad_first=bad_first;self.block=block
    def complete_json(self,*args):
        self.timer.advance(2)
        if self.block:
            charge(self.ledger,'.02',uncertain=True);raise BudgetExceeded('fake outstanding reservation')
        charge(self.ledger)
        result=super().complete_json(*args)
        if self.bad_first and len(self.requests)==1:result['unexpected_extra']='must be rejected'
        return result


def execution(ledger,timer,*,block=None):
    def run(package,ir):
        timer.advance(1)
        if block is not None and block['enabled'] and block['calls']==1:
            block['calls']+=1;charge(ledger,'.02',uncertain=True)
            raise BudgetExceeded('fake partial evaluation budget stop')
        if block is not None:block['calls']+=1
        if ledger is not None:charge(ledger,'.01',prompt=2,completion=1)
        return check_programs(ir,base_analysis(ir),[package])
    return run


def test_each_evaluated_round_records_actual_shared_ledger_and_time_deltas(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200');charge(ledger,'.4')
    result=run_feedback_loop(TASK,make_cases(tmp_path),client=Metered(ledger,timer),
        output_dir=tmp_path/'loop',runner=execution(ledger,timer),max_rounds=2,defer_test=True)
    assert result['status']=='selected_pending_test' and result['rounds_completed']==2
    usages=[row['resource_usage'] for row in result['rounds']]
    assert usages[0]['budget_before']['spent_cny']=='0.400000'
    assert usages[1]['budget_before']==usages[0]['budget_after']
    for usage in usages:
        assert usage['available'] is True and usage['accounting_scope']=='shared_ledger_interval'
        assert usage['elapsed_seconds']==6
        assert usage['spent_cny_delta']=='0.140000' and usage['committed_cny_delta']=='0.140000'
        assert usage['requests_delta']==5 and usage['prompt_tokens_delta']==18 and usage['completion_tokens_delta']==9
    assert ledger.summary()['spent_cny']=='0.680000'


def test_failed_candidate_has_real_cost_without_fabricating_an_evaluation(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200')
    result=run_feedback_loop(TASK,make_cases(tmp_path),client=Metered(ledger,timer,bad_first=True),
        output_dir=tmp_path/'loop',runner=execution(ledger,timer),max_rounds=2,defer_test=True)
    failed=result['rounds'][0]
    assert failed['status']=='candidate_failed' and 'validation_metrics' not in failed
    assert failed['resource_usage']['spent_cny_delta']=='0.100000'
    assert failed['resource_usage']['requests_delta']==1 and failed['resource_usage']['elapsed_seconds']==2
    assert result['rounds'][1]['resource_usage']['spent_cny_delta']=='0.140000'


def test_no_ledger_keeps_measured_elapsed_but_all_cost_and_counter_fields_null(tmp_path,monkeypatch):
    timer=clock(monkeypatch)
    class NoLedger(ExternalModel):
        def complete_json(self,*args):timer.advance(2);return super().complete_json(*args)
    result=run_feedback_loop(TASK,make_cases(tmp_path),client=NoLedger(),output_dir=tmp_path/'loop',
        runner=execution(None,timer),max_rounds=2,defer_test=True)
    for row in result['rounds']:
        usage=row['resource_usage']
        assert usage['available'] is False and usage['elapsed_seconds']==6
        for name in ['budget_before','budget_after','spent_cny_delta','committed_cny_delta',
                     'requests_delta','prompt_tokens_delta','completion_tokens_delta']:
            assert usage[name] is None


def test_budget_interrupted_round_saves_partial_usage_then_resumes_same_round_without_offline_wait(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200');model=Metered(ledger,timer)
    block={'enabled':True,'calls':0};manifest=make_cases(tmp_path)
    kwargs={'client':model,'output_dir':tmp_path/'loop','runner':execution(ledger,timer,block=block),
            'max_rounds':2,'defer_test':True}
    first=run_feedback_loop(TASK,manifest,**kwargs)
    assert first['status']=='incomplete' and first['rounds_completed']==0
    folder=tmp_path/'loop/round-000'
    assert not (folder/'round.json').exists() and not (tmp_path/'loop/selected.json').exists()
    usage=json.loads((folder/'resource-usage.json').read_text())['resource_usage']
    assert usage['spent_cny_delta']=='0.110000' and usage['committed_cny_delta']=='0.130000'
    assert usage['requests_delta']==3 and usage['elapsed_seconds']==4
    assert first['pending_round']['round']==0 and first['pending_round']['resource_usage']==usage
    timer.advance(10000);block['enabled']=False
    second=run_feedback_loop(TASK,manifest,**kwargs)
    resumed=second['rounds'][0]['resource_usage']
    assert second['rounds_completed']==2 and len(model.requests)==2
    assert resumed['budget_before']==usage['budget_before']
    assert resumed['spent_cny_delta']=='0.150000' and resumed['committed_cny_delta']=='0.170000'
    assert resumed['requests_delta']==7 and resumed['elapsed_seconds']==8
    assert second['rounds'][1]['resource_usage']['elapsed_seconds']==6


def test_reusing_a_completed_round_never_rewrites_its_resource_history(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200');model=Metered(ledger,timer,block=True)
    initial=build_program(candidate("def detect(payload):\n    return [emit(n,'PASS','initial','text',['test']) for n in nodes(payload,'BibliographyEntry')]"),
        rule_text='Hello',basis=TASK['basis'])
    manifest=make_cases(tmp_path)
    kwargs={'client':model,'output_dir':tmp_path/'loop','runner':execution(ledger,timer),
            'initial_package':initial,'max_rounds':2,'defer_test':True}
    first=run_feedback_loop(TASK,manifest,**kwargs)
    assert first['rounds_completed']==1 and first['stop_reason']=='budget_limit'
    folder=tmp_path/'loop/round-000';before={p.name:p.read_bytes() for p in [folder/'round.json',folder/'resource-usage.json']}
    assert first['rounds'][0]['resource_usage']['spent_cny_delta']=='0.040000'
    timer.advance(5000);model.block=False
    second=run_feedback_loop(TASK,manifest,**kwargs)
    assert second['status']=='selected_pending_test' and second['rounds_completed']==2
    assert before=={name:(folder/name).read_bytes() for name in before}
    assert second['rounds'][0]['resource_usage']==first['rounds'][0]['resource_usage']


def test_resource_interval_discloses_concurrent_ledger_spend_without_claiming_precise_attribution(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200')
    client=type('Client',(),{'ledger':ledger})()
    with accounting().ResourceInterval(client,tmp_path/'usage.json') as interval:
        timer.advance(3);charge(ledger,'.2')
        # This other ledger instance represents concurrent, unrelated work.
        charge(BudgetLedger(ledger.path,'200'),'.3')
    usage=interval.resource_usage
    assert usage['spent_cny_delta']=='0.500000' and usage['requests_delta']==2
    assert usage['accounting_scope']=='shared_ledger_interval' and usage['elapsed_seconds']==3


def test_interrupted_resource_context_preserves_active_usage_without_creating_a_completed_record(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200');client=type('Client',(),{'ledger':ledger})()
    with pytest.raises(SystemExit):
        with accounting().ResourceInterval(client,tmp_path/'usage.json'):
            charge(ledger,'.2',uncertain=True);timer.advance(4);raise SystemExit('simulated interrupted worker')
    state=json.loads((tmp_path/'usage.json').read_text())
    assert state['status']=='interrupted' and state['resource_usage']['elapsed_seconds']==4
    timer.advance(9000)
    with accounting().ResourceInterval(client,tmp_path/'usage.json') as resumed:
        timer.advance(2);charge(ledger,'.1')
    assert resumed.resource_usage['elapsed_seconds']==6
    assert resumed.resource_usage['committed_cny_delta']=='0.300000'
    assert resumed.resource_usage['spent_cny_delta']=='0.100000'


def test_resource_resume_cannot_switch_to_a_fresh_ledger(tmp_path,monkeypatch):
    timer=clock(monkeypatch);client=type('Client',(),{'ledger':BudgetLedger(tmp_path/'old.db','200')})()
    with accounting().ResourceInterval(client,tmp_path/'usage.json'):
        timer.advance(1);charge(client.ledger,'.1')
    client.ledger=BudgetLedger(tmp_path/'fresh.db','200')
    with pytest.raises(ValueError,match='ledger'):
        accounting().ResourceInterval(client,tmp_path/'usage.json')


def test_study_resume_preserves_first_start_and_budget_and_accumulates_only_active_time(tmp_path,monkeypatch):
    timer=clock(monkeypatch);ledger=BudgetLedger(tmp_path/'ledger.db','200');charge(ledger,'.4')
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    class StudyMeter(StudyModel):
        blocked=True
        def __init__(self):super().__init__();self.ledger=ledger
        def complete_json(self,*args):
            timer.advance(2)
            if self.requests and self.blocked:
                charge(ledger,'.02',uncertain=True);raise BudgetExceeded('fake reserved budget stop')
            charge(ledger);return super().complete_json(*args)
    model=StudyMeter();base=runner_for(out,splits,calls)
    def run(package,ir):
        timer.advance(1);charge(ledger,'.01',prompt=2,completion=1);return base(package,ir)
    run.study_fingerprint='metered-study-test/1'
    from paper_compiler.study import run_study
    first=run_study(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    assert first['status']=='incomplete' and 'budget' in first['stop_reason']
    assert first['resource_usage']['elapsed_seconds']==10
    initial=copy.deepcopy(first['initial']['only']['resource_usage'])
    assert initial['spent_cny_delta']=='0.100000' and initial['elapsed_seconds']==2
    start=first['started_at'];before=copy.deepcopy(first['budget_before'])
    assert before['spent_cny']=='0.400000'
    timer.advance(20000);model.blocked=False
    final=run_study(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    assert final['status']=='completed' and final['started_at']==start and final['budget_before']==before
    assert final['elapsed_seconds']==final['resource_usage']['elapsed_seconds']==38
    assert final['resource_usage']['spent_cny_delta']=='0.600000'
    assert final['resource_usage']['committed_cny_delta']=='0.620000'
    assert final['resource_usage']['budget_after']==final['budget']
    assert final['initial']['only']['resource_usage']==initial
    for condition in ['joint','program_only']:
        zero=final['conditions'][condition]['rules']['only']['rounds'][0]['resource_usage']
        assert zero['spent_cny_delta']=='0.060000', 'shared initial preparation cost must not be counted in reused round zero'
    frozen=json.loads((out/'summary.json').read_text())
    charge(ledger,'.2');timer.advance(10000)
    again=run_study(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    assert again==frozen and again['budget_before']==before


def test_snapshot_failure_is_unknown_instead_of_a_fabricated_zero_cost(tmp_path,monkeypatch):
    timer=clock(monkeypatch)
    class UnavailableLedger:
        def summary(self):raise OSError('ledger temporarily unavailable')
    client=type('Client',(),{'ledger':UnavailableLedger()})()
    with accounting().ResourceInterval(client,tmp_path/'usage.json') as interval:timer.advance(2)
    assert interval.resource_usage['available'] is False
    assert interval.resource_usage['budget_before'] is None and interval.resource_usage['spent_cny_delta'] is None


def test_study_cannot_replace_an_unknown_first_snapshot_with_a_later_visible_ledger(tmp_path,monkeypatch):
    timer=clock(monkeypatch);tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    model=StudyModel(budget_after=0);run=runner_for(out,splits,calls)
    from paper_compiler.study import run_study
    first=run_study(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=1)
    assert first['status']=='incomplete' and first['budget_before']['available'] is False
    first_before=copy.deepcopy(first['budget_before'])
    model.ledger=BudgetLedger(tmp_path/'existing-ledger.db','200');charge(model.ledger,'.3')
    model.budget_after=None;timer.advance(5000)
    final=run_study(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=1)
    assert final['status']=='completed' and final['budget_before']==first_before
    assert final['resource_usage']['available'] is False
    assert final['resource_usage']['budget_before'] is None and final['resource_usage']['spent_cny_delta'] is None
    assert final['resource_usage']['budget_after']['spent_cny']=='0.300000'


def test_budget_snapshot_only_exports_public_accounting_values(tmp_path,monkeypatch):
    timer=clock(monkeypatch)
    class Ledger:
        def summary(self):
            return {'spent_cny':'1.000000','committed_cny':'1.500000','requests':2,
                    'MAAS_API_KEY':'never-export-this','private_document':'never-export-this'}
    client=type('Client',(),{'ledger':Ledger()})()
    with accounting().ResourceInterval(client,tmp_path/'usage.json') as interval:timer.advance(1)
    assert 'never-export-this' not in json.dumps(interval.resource_usage)
    assert 'never-export-this' not in (tmp_path/'usage.json').read_text()
    assert interval.resource_usage['prompt_tokens_delta'] is None
