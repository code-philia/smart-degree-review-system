import copy
from paper_compiler import program_analysis as runtime
from test_paper_compiler_program_analysis import Model,package
from test_paper_compiler_program_analysis_batch import paper,run

class FlatModel(Model):
    json_output=True
    def __init__(self,bad=False):
        super().__init__();self.calls=0;self.bad=bad
    def complete_json(self,task,instructions,data,max_tokens):
        if task=='bibliography-fields/1.1':return super().complete_json(task,instructions,data,max_tokens)
        assert task=='grounded-observations-flat/1.0'
        assert data['schema_version']==task
        self.calls+=1
        sources={s['source_id']:s for s in data['sources']};observations=[]
        for item in data['nodes']:
            nid=item['node']['id'];src=next(sources[x] for x in item['source_ids'] if sources[x].get('node_id')==nid)
            observations.append({'node_id':nid,'field':'method','state':'observed','value':'tree models','quotes':[{'source_id':src['source_id'],'quote':'invented evidence' if self.bad and nid=='p1' else 'tree models'}]})
        return {'observations':observations}

def test_flat_observations_keep_grounded_per_node_fields_and_cache(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    ir=paper(tmp_path,2);model=FlatModel();before=copy.deepcopy(ir)
    result=run(tmp_path,ir,model)
    assert all(f['method']['state']=='observed' for f in result['results']['method_facts'].values())
    assert model.calls==1 and ir==before
    assert run(tmp_path,ir,model)==result and model.calls==1
    assert result['policy']['generated_batch']['task']=='grounded-observations-flat/1.0'

def test_flat_decoder_does_not_make_invented_quote_evidence(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    result=run(tmp_path,paper(tmp_path,2),FlatModel(bad=True))
    assert result['results']['method_facts']['p0']['method']['state']=='observed'
    assert result['results']['method_facts']['p1']['method']['state']=='unknown'


def test_unusable_semantic_response_is_unknown_without_retry(tmp_path,monkeypatch):
    from paper_compiler.llm import ModelError
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    class Broken(FlatModel):
        def complete_json(self,*args):
            self.calls+=1
            raise ModelError('model request failed: invalid_output')
    model=Broken();result=run(tmp_path,paper(tmp_path,2),model)
    assert model.calls==1
    assert all(x['method']['state']=='unknown' for x in result['results']['method_facts'].values())
