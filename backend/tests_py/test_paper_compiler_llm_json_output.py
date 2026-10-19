import hashlib
from decimal import Decimal
from paper_compiler.llm import MaasClient
from paper_compiler.budget import BudgetLedger
from paper_compiler.storage import json_bytes
from test_paper_compiler_llm import config,response

def test_json_constraint_uses_actual_wire_key_cache_and_existing_ledger(tmp_path):
    sent=[]
    ledger=BudgetLedger(tmp_path/'budget.db',Decimal('10'))
    def transport(url,headers,payload,timeout):
        sent.append(payload)
        return response('{"results":{"node":{"fields":{"relation":{"state":"unknown"}}}}}')
    common=(config(tmp_path),ledger,tmp_path/'cache','json-contract','5')
    normal=MaasClient(*common,transport=transport,max_attempts=1)
    constrained=MaasClient(*common,transport=transport,max_attempts=1,json_output=True)
    data={'nodes':[{'id':'node'}]}
    for client in [normal,constrained,constrained]:
        assert client.complete_json('generated-analysis-batch/1.0','Return JSON',data,100)['results']['node']['fields']['relation']['state']=='unknown'
    assert len(sent)==2
    assert 'response_format' not in sent[0]
    assert sent[1]['response_format']=={'type':'json_object'}
    a=normal.request_fingerprint('generated-analysis-batch/1.0','Return JSON',data,100)
    b=constrained.request_fingerprint('generated-analysis-batch/1.0','Return JSON',data,100)
    assert a!=b and sent[1]==b['payload']
    key=hashlib.sha256(json_bytes(b)).hexdigest()
    assert (tmp_path/'cache/responses'/(key+'.json')).is_file()
    assert ledger.summary()['requests']==2
    assert ledger.summary()['spent_cny']=='0.001200'

    assert normal.request_fingerprint('bibliography-fields/1.1','Return JSON',data,100)==constrained.request_fingerprint('bibliography-fields/1.1','Return JSON',data,100)
