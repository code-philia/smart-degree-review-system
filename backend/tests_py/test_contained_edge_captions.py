from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.native_layout import in_margin


def obj(kind, box, text=''):
    return LayoutObject(kind, 60, box, text, 595, 842)


def test_chart_boundary_can_include_its_own_complete_caption():
    first=obj('figure',(85,219,517,381))
    second=obj('figure',(89,407,511,583))
    cap1=obj('figure_caption',(140,386,451,401),'图6-1 方法比较')
    cap2=obj('figure_caption',(139,569,450,583),'图6-2 性能比较')
    assert not detect_caption_rules([first,second,cap1,cap2],[13])['13']['findings']


def test_removing_one_title_retains_the_other_charts_missing_title():
    first=obj('figure',(85,219,517,381))
    second=obj('figure',(89,407,511,583))
    cap2=obj('figure_caption',(139,569,450,583),'图6-2 性能比较')
    findings=detect_caption_rules([first,second,cap2],[13])['13']['findings']
    assert len(findings)==1
    assert findings[0]['location']['bounding_rect']['y1']==219


def test_caption_in_the_middle_of_a_larger_diagram_cannot_title_the_container():
    target=obj('figure',(80,100,520,600))
    title=obj('figure_caption',(140,340,450,354),'图6-2 某个内部示例')
    assert len(detect_caption_rules([target,title],[13])['13']['findings'])==1


def test_rotated_top_barcode_is_margin_content_in_display_frame():
    assert in_margin((0,161,30,253),842,595,display_rotation=90)
    assert not in_margin((260,161,290,253),842,595,display_rotation=90)


def test_rotated_bottom_barcode_and_unrotated_body_image_stay_distinct():
    assert in_margin((811,161,842,253),842,595,display_rotation=90)
    assert not in_margin((0,161,30,253),842,595)


def test_complete_bilingual_title_may_cross_the_cropped_plot_edge():
    target=obj('figure',(80,100,520,319))
    title=obj('figure_caption',(100,306,500,337),'图2.8 参数对比 Figure 2.8 Comparison')
    assert not detect_caption_rules([target,title],[13])['13']['findings']


def test_vertical_bilingual_title_may_cross_the_cropped_plot_edge():
    target=obj('figure',(80,100,319,600))
    title=obj('figure_caption',(306,180,337,550),'图2.8 参数对比 Figure 2.8 Comparison')
    assert not detect_caption_rules([target,title],[13])['13']['findings']


def test_wide_bilingual_title_crossing_a_shallow_plot_edge_is_owned():
    target=obj('figure',(111.052,430.455,458.216,590.822))
    title=obj('figure_caption',(68.032,577.611,510.240,608.643),
              '图2-8 参数比较 Figure 2-8 Parameter comparison')
    assert not detect_caption_rules([target,title],[13])['13']['findings']


def test_wide_bilingual_title_at_the_middle_cannot_title_a_shallow_plot():
    target=obj('figure',(111.052,430.455,458.216,590.822))
    title=obj('figure_caption',(68.032,490,510.240,521),
              '图2-8 参数比较 Figure 2-8 Parameter comparison')
    assert detect_caption_rules([target,title],[13])['13']['findings']
