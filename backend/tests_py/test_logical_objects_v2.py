"""Object identity regressions from inspected original PDF layouts."""
from pathlib import Path
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage


def obj(kind, box, text='', role='', page=1):
    return LayoutObject(kind, page, box, text, 600, 840, role)


def line(text, box, page=1):
    return PdfLine(page, text, box, 600, 840)


def check(objects, lines=(), pages=None, images=(), tables=()):
    document = PdfDocument(Path('unseen-layout.pdf'), tuple(pages or [
        PdfPage(1, 600, 840, tuple(lines), images=tuple(images), tables=tuple(tables))]))
    layout = prepare_caption_layout(objects, document)
    return detect_caption_rules(layout, [13, 14], document)


def test_stacked_charts_with_shared_axis_and_one_caption_are_one_figure():
    objects = [obj('figure', (100, y, 500, y+130), role='chart_body') for y in (100, 242)]
    objects.append(obj('figure_caption', (190, 388, 420, 403), 'Figure 8.2 Expert comparison'))
    lines = [line('Number of experts', (260, y+119, 360, y+132)) for y in (100, 242)]
    assert check(objects, lines)['13']['findings'] == []


def test_unlabelled_multiline_chart_grid_uses_shared_axis_not_caption_width():
    objects = [obj('figure', (x, y, x+125, y+105), role='chart_body')
               for x in (80, 230, 380) for y in (100, 216)]
    lines = [line('Time (s)', (x+45, y+92, x+85, y+104))
             for x in (80, 230, 380) for y in (100, 216)]
    objects.append(obj('figure_caption', (245, 339, 345, 354), 'Figure 8.2 Features'))
    assert check(objects, lines)['13']['findings'] == []


def test_chart_grid_with_only_numeric_tick_matches_keeps_missing_titles():
    objects = [obj('figure', (x, 100, x+125, 205), role='chart_body') for x in (80, 230, 380)]
    lines = [line('0 1 2 3', (x+45, 192, x+85, 204)) for x in (80, 230, 380)]
    objects.append(obj('figure_caption', (245, 220, 345, 235), 'Figure 8.2 One result'))
    assert len(check(objects, lines)['13']['findings']) == 2


def test_independent_chart_caption_is_a_boundary_even_with_shared_axes():
    objects = [obj('figure', (100, y, 500, y+130), role='chart_body') for y in (100, 242)]
    objects.append(obj('figure_caption', (190, 232, 420, 244), 'Figure 8.2 First result'))
    lines = [line('Number of experts', (260, y+116, 360, y+128)) for y in (100, 242)]
    assert len(check(objects, lines)['13']['findings']) == 1


def test_bilingual_subpanel_descriptions_are_not_label_restarts():
    objects = [obj('figure', (x, y, x+125, y+105), role='chart_body')
               for x in (80, 230, 380) for y in (100, 216)]
    lines = [line('Time (s)', (x+45, y+92, x+85, y+104))
             for x in (80, 230, 380) for y in (100, 216)]
    for x, tag in zip((80, 230, 380), 'abc'):
        lines.extend([line(f'({tag}) 第一组实验', (x, 335, x+125, 348)),
                      line(f'({tag}) First experiment', (x, 365, x+125, 378))])
    objects.append(obj('figure_caption', (245, 395, 345, 410), 'Figure 8.2 Features'))
    assert check(objects, lines)['13']['findings'] == []


def test_restarted_subpanel_on_separate_chart_is_still_a_boundary():
    objects = [obj('figure', (100, y, 500, y+130), role='chart_body') for y in (100, 242)]
    lines = [line('Time (s)', (270, y+105, 335, y+119)) for y in (100, 242)]
    lines += [line('(a)', (280, y+120, 300, y+132)) for y in (100, 242)]
    objects.append(obj('figure_caption', (190, 388, 420, 403), 'Figure 8.2 One experiment'))
    assert len(check(objects, lines)['13']['findings']) == 1


def test_picture_table_with_table_caption_is_not_an_untitled_figure():
    objects = [obj('figure', (80, 200, 520, 440), role='image_body'),
               obj('table_caption', (170, 180, 430, 194), 'Table 8.2 Molecular editing', role='image_caption')]
    lines = [line(text, (x, 214, x+65, 227))
             for x, text in [(100, 'Input'), (210, 'Output'), (320, 'Input'), (430, 'Output')]]
    result = check(objects, lines, images=[(90, 240, 190, 420), (200, 240, 300, 420),
                                         (310, 240, 410, 420), (420, 240, 520, 420)])
    assert result['13']['findings'] == [] and result['14']['findings'] == []


def test_table_caption_owned_by_neighbor_cannot_reclassify_missing_figure():
    objects = [obj('table', (80, 200, 520, 350), role='table_body'),
               obj('table_caption', (170, 180, 430, 194), 'Table 8.2 Results'),
               obj('figure', (80, 95, 520, 160), role='image_body')]
    assert len(check(objects)['13']['findings']) == 1


def test_mirrored_page_table_repeats_headers_but_running_header_is_not_body():
    objects = [obj('table', (90, 140, 530, 720), role='table_body'),
               obj('table_caption', (180, 118, 440, 132), 'Table 8.2 Related work'),
               obj('table', (75, 99, 515, 350), role='table_body', page=2)]
    pages = []
    for p, x, y in [(1, 90, 140), (2, 75, 99)]:
        lines = [line('University thesis', (x, 76, x+130, 87), p)]
        lines += [line(t, (x+off, y+4, x+off+80, y+17), p)
                  for off, t in [(5, 'Field'), (100, 'Algorithm'), (240, 'Venue'), (340, 'Method')]]
        pages.append(PdfPage(p, 600, 840, tuple(lines)))
    assert check(objects, pages=pages)['14']['findings'] == []


def test_repeated_table_header_cannot_cross_body_paragraph():
    objects = [obj('table', (90, 140, 530, 720), role='table_body'),
               obj('table_caption', (180, 118, 440, 132), 'Table 8.2 Related work'),
               obj('table', (75, 110, 515, 350), role='table_body', page=2)]
    pages = []
    for p, x, y in [(1, 90, 140), (2, 75, 110)]:
        lines = [line(t, (x+off, y+4, x+off+80, y+17), p)
                 for off, t in [(5, 'Field'), (100, 'Algorithm'), (240, 'Venue')]]
        if p == 2:
            lines.append(line('Here we introduce an independent experiment.', (75, 91, 500, 104), p))
        pages.append(PdfPage(p, 600, 840, tuple(lines)))
    assert len(check(objects, pages=pages)['14']['findings']) == 1


def test_parenthesized_time_unit_is_not_a_restarted_subpanel_tag():
    objects = [obj('figure', (x, 100, x+125, 205), role='chart_body') for x in (80, 230, 380)]
    lines = []
    for x in (80, 230, 380):
        lines.append(line('(s)', (x+55, 194, x+70, 204)))
        lines += [line(str(k), (x+15+k*25, 184, x+22+k*25, 191)) for k in range(4)]
    objects.append(obj('figure_caption', (235, 220, 355, 234), 'Figure 8.2 Timing'))
    assert check(objects, lines)['13']['findings'] == []


def test_tiny_caption_descender_overlap_does_not_remove_a_real_table_title():
    objects = [obj('table', (80, 116, 520, 595), role='table_body'),
               obj('table_caption', (260, 106, 350, 119), 'Table 8.2 Comparison')]
    assert check(objects)['14']['findings'] == []


def test_numeric_rows_continue_across_page_without_repeated_table_header():
    objects = [obj('table', (80, 620, 520, 704), role='table_body'),
               obj('table_caption', (180, 597, 440, 614), 'Table 8.2 Timing'),
               obj('table', (80, 100, 520, 220), role='table_body', page=2)]
    first = [line(t, (x, 625, x+60, 637)) for x,t in [(100,'Batch'),(220,'Time'),(340,'Cost'),(450,'Total')]]
    first += [line(str(v), (x, 688, x+40, 700)) for x,v in [(100,300),(220,123),(340,234),(450,357)]]
    second = [line(str(v), (x, y, x+40, y+12), 2)
              for y, values in [(104,[400,456,567,1023]),(145,[500,678,789,1467]),(186,[600,901,1023,1924])]
              for x,v in zip((100,220,340,450),values)]
    pages = [PdfPage(1,600,840,tuple(first)),PdfPage(2,600,840,tuple(second))]
    assert check(objects,pages=pages)['14']['findings'] == []


def test_numeric_table_restart_is_not_a_cross_page_continuation():
    objects = [obj('table', (80, 620, 520, 704), role='table_body'),
               obj('table_caption', (180, 597, 440, 614), 'Table 8.2 Timing'),
               obj('table', (80, 100, 520, 220), role='table_body', page=2)]
    first = [line(str(v), (x, 688, x+40, 700)) for x,v in [(100,300),(220,123),(340,234),(450,357)]]
    second = [line(str(v), (x, y, x+40, y+12), 2)
              for y, values in [(104,[100,456,567,1023]),(145,[200,678,789,1467])]
              for x,v in zip((100,220,340,450),values)]
    assert len(check(objects,pages=[PdfPage(1,600,840,tuple(first)),PdfPage(2,600,840,tuple(second))])['14']['findings']) == 1


def test_symbol_table_running_heading_identifies_continuation_page():
    objects = [obj('table',(150,100,455,695),role='table_body')]
    lines = [line('符号对照表',(480,74,525,83)),line('alpha',(160,110,190,125)),line('Attention weight',(280,110,390,125))]
    assert check(objects,lines)['14']['findings'] == []


def test_staggered_last_chart_row_and_axis_units_are_one_grid():
    boxes = [(x,y,x+112,y+105) for y in (100,210) for x in (135,247,359)]
    boxes += [(x,320,x+112,425) for x in (80,192,304,416)]
    objects = [obj('figure',b,role='chart_body') for b in boxes]
    lines=[]
    for x,y,_,_ in boxes:
        lines.append(line('(s)',(x+50,y+93,x+66,y+104)))
        lines += [line(str(k),(x+12+k*25,y+82,x+19+k*25,y+89)) for k in range(4)]
    objects.append(obj('figure_caption',(170,438,440,454),'Figure 8.2 Spectral response'))
    assert check(objects,lines)['13']['findings'] == []


def test_labelled_columns_can_have_different_axes_under_one_global_title():
    objects=[obj('figure',(x,y,x+125,y+105),role='chart_body') for x in (80,230,380) for y in (100,216)]
    lines=[line('Time (s)' if x<380 else 'Frequency (Hz)',(x+25,y+92,x+100,y+104)) for x in (80,230,380) for y in (100,216)]
    lines += [line(f'({tag}) A comparison',(x,335,x+125,348)) for x,tag in zip((80,230,380),'abc')]
    objects.append(obj('figure_caption',(240,392,350,407),'Figure 8.2 Features'))
    assert check(objects,lines)['13']['findings']==[]


def test_coloured_multiline_legend_beside_chart_is_a_figure_component():
    objects=[obj('table',(80,140,190,205),'P: memory D: memory P: compute D: compute',role='table_body'),
             obj('figure',(205,120,500,235),role='chart_body'),
             obj('figure_caption',(185,250,410,265),'Figure 8.2 Performance')]
    lines=tuple(line(t,(110,y,180,y+10)) for t,y in [('P: memory',145),('D: memory',160),('P: compute',175),('D: compute',190)])
    marks=tuple((85,y+3,104,y+7) for y in (145,160,175,190))
    page=PdfPage(1,600,840,lines,legend_marks=marks)
    r=check(objects,pages=[page])
    assert r['13']['findings']==[] and r['14']['findings']==[]


def test_numeric_table_beside_chart_is_not_a_legend():
    objects=[obj('table',(80,140,190,205),'A 0.95 B 0.98',role='table_body'),
             obj('figure',(205,120,500,235),role='chart_body'),
             obj('figure_caption',(185,250,410,265),'Figure 8.2 Performance')]
    lines=tuple(line(t,(110,y,180,y+10)) for t,y in [('A 0.95',145),('B 0.98',160)])
    page=PdfPage(1,600,840,lines,legend_marks=((85,148,104,152),(85,163,104,167)))
    assert len(check(objects,pages=[page])['14']['findings'])==1


def test_labelled_interface_and_code_panels_form_one_captioned_screenshot():
    objects=[obj('figure',(90,105,125,135),role='image_body'),
             obj('text',(135,105,495,120),'Project issue tracker',role='title'),
             obj('text',(135,125,490,145),'Unexpected error on valid input',role='title'),
             obj('table',(85,160,510,235),'Type: Bug Status: Open Priority: Low Resolution: Unresolved',role='table_body'),
             obj('text',(85,285,510,370),'def run(): return result',role='code_body'),
             obj('figure_caption',(190,405,430,420),'Figure 8.2 Interface and patch')]
    lines=[line('(a) Issue details',(240,249,350,262)),line('(b) Source patch',(240,380,350,393))]
    r=check(objects,lines)
    assert r['13']['findings']==[] and r['14']['findings']==[]


def test_interface_like_table_with_own_table_title_stays_a_table():
    objects=[obj('figure',(90,105,125,135),role='image_body'),
             obj('text',(135,105,495,120),'Project issue tracker',role='title'),
             obj('table',(85,160,510,235),'Type: Bug Status: Open Priority: Low',role='table_body'),
             obj('table_caption',(190,140,440,154),'Table 8.2 Field definition'),
             obj('text',(85,285,510,370),'def run(): return result',role='code_body'),
             obj('figure_caption',(190,405,430,420),'Figure 8.2 Source patch')]
    r=check(objects,[line('(a) Details',(240,249,350,262)),line('(b) Source patch',(240,380,350,393))])
    assert len(r['13']['findings'])==1 and r['14']['findings']==[]


def test_invisible_native_rule_window_outside_figure_is_not_a_table(tmp_path):
    import pymupdf
    path=tmp_path/'clipped.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=840)
        p.draw_rect((100,100,400,300))
        p.draw_rect((300,130,390,210))
        pdf.save(path)
    page=PdfPage(1,600,840,(),tables=((280,130,480,220),))
    doc=PdfDocument(path,(page,))
    objects=[obj('figure',(100,100,400,300),role='image_body'),obj('figure_caption',(180,315,350,330),'Figure 8.2 Architecture')]
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']==[]


def test_visible_table_ink_outside_neighbor_figure_is_kept(tmp_path):
    import pymupdf
    path=tmp_path/'visible.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=840)
        p.draw_rect((100,100,400,300))
        p.draw_rect((300,130,390,210))
        p.draw_rect((415,130,480,220))
        p.insert_text((420,150),'A 12')
        pdf.save(path)
    page=PdfPage(1,600,840,(),tables=((280,130,480,220),))
    doc=PdfDocument(path,(page,))
    objects=[obj('figure',(100,100,400,300),role='image_body'),obj('figure_caption',(180,315,350,330),'Figure 8.2 Architecture')]
    assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings'])==1


def test_translated_panel_label_in_gap_is_not_assigned_to_the_next_chart():
    objects=[obj('figure',(120,100,475,214),role='chart_body'),obj('figure',(100,274,445,386),role='chart_body'),
             obj('figure_caption',(80,445,500,473),'Figure 8.2 Measurements')]
    lines=[line('(a) 延迟与吞吐量',(250,242,330,253)),line('(a) Latency and throughput',(233,256,348,267)),
           line('(b) 内存压力',(226,414,353,425)),line('(b) Memory pressure',(202,428,380,439))]
    assert check(objects,lines)['13']['findings']==[]


def test_partial_grid_titles_cannot_hide_an_untitled_neighbor():
    objects=[obj('figure',(x,100,x+125,205),role='chart_body') for x in (80,230,380)]
    lines=[line('Time (s)',(x+45,192,x+85,204)) for x in (80,230,380)]
    objects += [obj('figure_caption',(80,220,205,235),'Figure 8.1 First result'),
                obj('figure_caption',(235,220,350,235),'Figure 8.2 Second result')]
    found=check(objects,lines)['13']['findings']
    assert len(found)==1 and found[0]['location']['bounding_rect']['x1']==380


def test_conflicting_header_blocks_apparent_numeric_row_continuation():
    objects=[obj('table',(80,620,520,704),role='table_body'),
             obj('table_caption',(180,597,440,614),'Table 8.2 Timing'),
             obj('table',(80,100,520,220),role='table_body',page=2)]
    first=[line(t,(x,625,x+60,637)) for x,t in zip((100,220,340,450),('Batch','Time','Cost','Total'))]
    first += [line(str(v),(x,688,x+40,700)) for x,v in zip((100,220,340,450),(300,123,234,357))]
    second=[line(t,(x,104,x+60,116),2) for x,t in zip((100,220,340,450),('Samples','Accuracy','Recall','F1'))]
    second += [line(str(v),(x,y,x+40,y+12),2) for y,values in [(145,[400,456,567,1023]),(186,[500,678,789,1467])]
               for x,v in zip((100,220,340,450),values)]
    r=check(objects,pages=[PdfPage(1,600,840,tuple(first)),PdfPage(2,600,840,tuple(second))])
    assert len(r['14']['findings'])==1 and r['14']['findings'][0]['page']==2


def test_neighboring_column_image_is_not_part_of_a_captioned_interface():
    objects=[obj('figure',(90,105,120,135),role='image_body'),
             obj('text',(125,105,280,120),'Project issue tracker',role='title'),
             obj('table',(85,160,285,235),'Type: Bug Status: Open Priority: Low Resolution: Unresolved',role='table_body'),
             obj('text',(85,285,285,370),'def run(): return result',role='code_body'),
             obj('figure',(390,285,585,370),role='image_body'),
             obj('figure_caption',(90,405,280,420),'Figure 8.2 Interface and patch')]
    lines=[line('(a) Issue details',(120,249,250,262)),line('(b) Source patch',(120,380,250,393))]
    found=check(objects,lines)['13']['findings']
    assert len(found)==1 and found[0]['location']['bounding_rect']['x1']==390
