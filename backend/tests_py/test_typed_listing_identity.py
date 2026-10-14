from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout


def check(texts,body_text='',role='table_body',heading='代码 8.4'):
    box=(70,120,520,280)
    lines=[PdfLine(1,heading,(180,90,420,104),600,840)]
    lines += [PdfLine(1,t,(90,130+i*18,500,144+i*18),600,840) for i,t in enumerate(texts)]
    doc=PdfDocument(Path('typed-listing.pdf'),(PdfPage(1,600,840,tuple(lines),graphics=(box,)),))
    body=LayoutObject('table',1,box,body_text,600,840,role)
    objects=[body]
    if role=='native_table':objects.append(LayoutObject('text',1,box,body_text,600,840,'code_body'))
    return detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)


def test_explicit_c_struct_listing_is_not_an_academic_table():
    lines=['1 struct Message {','2 ItemType type;','3 OpKind op;','4 uint64_t sequence;','5 Arguments args;','6 };']
    r=check(lines,'struct Message { ItemType type; OpKind op; uint64_t sequence; Arguments args; };')
    assert r['14']['findings']==[]


def test_chinese_schema_prompt_listing_owns_native_border_window():
    text='Listing 12 判定提示词\n1 [当前任务] 你现在处于 {task_prompt} 阶段。\n2 [输入] 当前轮次: {iteration_id}；模型: {model_state}\n3 [处理要求] 分析输入并判断变化范围。\n4 [输出要求] 仅返回 JSON: {"result": []}'
    r=check(text.splitlines(),text,'native_table','Listing 12 判定提示词')
    assert r['14']['findings']==[]


def test_comparison_rows_with_one_c_code_cell_remain_a_table():
    r=check(['Method Latency Result','baseline 24 struct Message { ItemType type; }','new 16 true'],'Method Latency Result baseline 24 struct Message { ItemType type; } new 16 true')
    assert len(r['14']['findings'])==1


def test_listing_narrative_cannot_exempt_a_separate_data_table():
    r=check(['Method Latency Result','baseline 24 true','new 16 true'],'Method Latency Result baseline 24 true new 16 true',heading='Listing 8.4 shows how these rows are computed.')
    assert len(r['14']['findings'])==1


def test_placeholder_data_columns_are_not_an_instruction_template():
    text='Name Value\nInput {first_input}\nOutput {result_value}\nModel {model_id}'
    r=check(text.splitlines(),text,'native_table','Listing 12 Parameter comparison')
    assert len(r['14']['findings'])==1
