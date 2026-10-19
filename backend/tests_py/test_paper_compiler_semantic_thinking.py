from decimal import Decimal
import json
import pytest
from paper_compiler.llm import MaasClient
from paper_compiler.budget import BudgetLedger
from test_paper_compiler_llm import config,response


@pytest.mark.parametrize('task,want',[
    ('grounded-observations-flat/1.0',True),
    ('generated-analysis/1.0',True),
    ('generated-analysis-batch/1.0',True),
    ('positive-conflict-review/1.0',True),
    ('paper-program-synthesis/2.0',False),
    ('paper-model-classification-batch/1.0',False),
    ('bibliography-fields/1.1',False)])
def test_semantic_thinking_is_sent_only_for_semantic_judgments(tmp_path,task,want):
    sent=[]
    def transport(url,headers,payload,timeout):
        sent.append(payload)
        return response()
    client=MaasClient(config(tmp_path),BudgetLedger(tmp_path/'budget.db',Decimal('10')),
        tmp_path/'cache','test',Decimal('10'),transport=transport,max_attempts=1,
        semantic_thinking=True,json_output=True)
    client.complete_json(task,'Observe supplied sources',{'sources':[]},100)
    assert sent[0]['chat_template_kwargs']['thinking'] is want
    record=json.loads(next((tmp_path/'cache/attempts').glob('*.json')).read_text())
    assert bool(record.get('semantic_thinking')) is want
    assert 'program_synthesis_thinking' not in record


def test_enabling_semantic_thinking_reuses_extraction_cache_but_not_old_judgment(tmp_path):
    sent=[]
    def transport(*args):
        sent.append(args[2])
        return response()
    ledger=BudgetLedger(tmp_path/'budget.db',Decimal('10'))
    old=MaasClient(config(tmp_path),ledger,tmp_path/'cache','test',Decimal('10'),
        transport=transport,max_attempts=1)
    new=MaasClient(config(tmp_path),ledger,tmp_path/'cache','test',Decimal('10'),
        transport=transport,max_attempts=1,semantic_thinking=True)
    for client in [old,new]:
        client.complete_json('bibliography-fields/1.1','Extract',{'entries':[]},100)
        client.complete_json('positive-conflict-review/1.0','Observe',{'sources':[]},100)
    assert len(sent)==3
    assert [v['chat_template_kwargs']['thinking'] for v in sent]==[False,False,True]
    assert ledger.summary()['requests']==3
