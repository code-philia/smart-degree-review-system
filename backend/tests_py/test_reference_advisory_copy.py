from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from paper_compiler.local_checks import detect_ir
from test_fast_local_checks import sample_ir

MESSAGE='按最新参考文献标准GB/T 7714-2025，文献类型或载体标记不在国标代码表中'
SUGGESTION='可按最新国家标准根据实际著录资源核对并补齐类型标记，所有参考文献标准统一用GB/T 7714-2025或GB/T 7714-2015，该检测项为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新'

def finding(marker):
    ir=sample_ir()
    node=next(n for n in ir['nodes'] if n['id']=='ref1')
    node['text']='[1] WANG A. A useful paper'+marker+'. Journal of Tests, 2020, 3: 1-9.'
    return detect_ir(ir,[31])['31']['findings']

def test_invalid_type_uses_requested_standard_and_advisory():
    result=finding('[B]')
    assert len(result)==1
    assert result[0]['message']==MESSAGE
    assert result[0]['suggestion']==SUGGESTION
    assert result[0]['token']=='文献类型标记'
    assert result[0]['location']['page_number']==8

def test_missing_type_keeps_accurate_reason_and_uses_same_advisory():
    result=finding('')
    assert len(result)==1
    assert result[0]['message']=='缺少完整的方括号文献类型标记'
    assert result[0]['suggestion']==SUGGESTION

def test_valid_type_remains_unflagged():
    assert finding('[J]')==[]
