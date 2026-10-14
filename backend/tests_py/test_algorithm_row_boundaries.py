from pdf_rules.model import PdfLine
from pdf_rules.text_fragments import merge_reference_fragments


def line(t,y):return PdfLine(1,t,(90,y,522,y+16),600,840,font_size=10.5)


def test_algorithm_row_number_cannot_complete_the_previous_comment_noun():
    lines=(line('6. V ← Zero(M) ▷ 初始化投票响应图',260),line('8. M ← Predict(I) ▷ 分割推理',292))
    assert len(merge_reference_fragments(lines))==2


def test_adjacent_program_statements_keep_their_row_identity():
    lines=(line('22. M ← Reconstruct(R) ▷ 重构二值图',520),line('23. R ← BoundaryDiff(A, B) ▷ 边界计算',537))
    assert len(merge_reference_fragments(lines))==2


def test_numbered_prose_still_recovers_a_genuine_wrapped_reference():
    lines=(line('6. 在统一数据上评估，结果如图',260),line('8.2 所示。两种方法采用相同的输入。',292))
    joined=merge_reference_fragments(lines)
    assert len(joined)==1
    assert '图 8.2' in joined[0].text
