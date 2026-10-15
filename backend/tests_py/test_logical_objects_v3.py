"""Generic regressions for physical fragments, listings, and title ownership."""
from pathlib import Path
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage


def obj(kind, box, text='', role=''):
    return LayoutObject(kind, 1, box, text, 600, 840, role)


def line(text, box):
    return PdfLine(1, text, box, 600, 840)


def check(objects, lines=(), images=(), tables=()):
    doc = PdfDocument(Path('independent-layout.pdf'), (PdfPage(
        1, 600, 840, tuple(lines), images=tuple(images), tables=tuple(tables)),))
    return detect_caption_rules(prepare_caption_layout(objects, doc), [13, 14], doc)


def test_neighboring_table_titles_reassign_instead_of_stranding_second_table():
    objects = [obj('table', (145, 390, 435, 460), role='table_body'),
               obj('table', (75, 510, 510, 580), role='table_body'),
               obj('table_caption', (160, 350, 420, 380), 'Table 4.2 First comparison'),
               obj('table_caption', (150, 469, 430, 498), 'Table 4.3 Second comparison')]
    assert check(objects)['14']['findings'] == []


def test_shared_row_labels_restore_all_grid_fragments():
    objects = [obj('figure', (x, y, x+180, y+100), role='chart_body')
               for x in (80, 300) for y in (100, 225, 350)]
    objects.append(obj('figure_caption', (70, 473, 515, 490), 'Figure 7.3 Comparing datasets'))
    lines = [line(f'({tag}) Dataset', (230, y+101, 350, y+114))
             for tag, y in zip('abc', (100, 225, 350))]
    assert check(objects, lines)['13']['findings'] == []


def test_touching_column_panels_merge_before_letter_sequence():
    objects = [obj('figure', (x, y, x+170, y+90), role='chart_body')
               for x in (110, 285) for y in (100, 192)]
    objects.append(obj('figure_caption', (80, 304, 510, 319), 'Figure 7.4 Joint comparison'))
    lines = [line(f'({tag})', (x+75, 282, x+90, 297)) for x,tag in [(110,'a'),(285,'b')]]
    assert check(objects, lines)['13']['findings'] == []


def test_shared_legend_is_part_of_labelled_composite():
    objects = [obj('figure', (x, y, x+180, y+100), role='chart_body')
               for x in (80, 300) for y in (100, 225)]
    objects += [obj('figure_caption', (70, 350, 515, 365), 'Figure 7.5 Experiments')]
    lines = [line(f'({tag}) Dataset', (x+30, y+102, x+145, y+115))
             for (x,y),tag in zip([(80,100),(300,100),(80,225),(300,225)],'abcd')]
    assert check(objects, lines, images=[(105, 100, 465, 118)])['13']['findings'] == []


def test_independent_missing_chart_outside_labelled_envelope_remains_reported():
    objects = [obj('figure', (80, 100, 260, 210), role='chart_body'),
               obj('figure', (300, 100, 480, 210), role='chart_body'),
               obj('figure', (80, 410, 480, 600), role='chart_body'),
               obj('figure_caption', (170, 240, 400, 255), 'Figure 7.6 Joint result')]
    lines = [line('(a) First', (120,212,210,230)),line('(b) Second',(350,212,440,230))]
    assert len(check(objects,lines)['13']['findings']) == 1


def test_numbered_listing_with_json_body_is_not_a_missing_figure():
    objects = [obj('figure', (70, 300, 520, 610), role='image_body')]
    lines = [line('Listing 8.2', (185, 625, 260, 640))]
    code = ['{', '"type": "record",', '"properties": {', '"name": "value"', '}', '}']
    lines += [line(t,(90,320+i*22,400,333+i*22)) for i,t in enumerate(code)]
    assert check(objects,lines)['13']['findings'] == []


def test_listing_mention_does_not_exempt_a_real_missing_figure():
    objects = [obj('figure', (70,300,520,610),role='image_body')]
    lines = [line('Listing 8.2 shows how this plot is computed.',(90,270,500,285))]
    assert len(check(objects,lines)['13']['findings']) == 1


def test_native_table_window_across_code_frame_is_not_a_table():
    objects = [obj('text',(80,400,385,465),
                   'if action == "open":\n    return client.open(value)\nelif action == "close":\n    return client.close(value)', 'code_body')]
    lines = [line('Each action calls the corresponding method:',(90,370,410,385))]
    lines += [line(t,(85,405+i*15,380,415+i*15)) for i,t in enumerate(objects[0].text.splitlines())]
    assert check(objects, lines, tables=[(70,360,520,470)])['14']['findings'] == []


def test_real_table_with_code_in_one_cell_remains_reported():
    objects = [obj('table',(70,360,520,600),role='table_body'),
               obj('text',(80,400,210,440),'if ready:\n    return run()', 'code_body')]
    lines = [line('Method',(90,370,140,385)),line('Accuracy',(300,370,380,385)),
             line('Baseline',(90,450,160,465)),line('87.6',(300,450,345,465))]
    assert len(check(objects,lines)['14']['findings']) == 1


def test_native_ui_fields_and_icon_share_caption_with_code_screenshot():
    objects = [obj('figure',(90,105,120,132),role='image_body'),
               obj('figure',(80,280,520,415),role='image_body'),
               obj('figure_caption',(180,425,430,440),'Figure 8.3 Issue and change')]
    lines = [line('Issue details',(130,105,430,130)),
             line('Type:',(110,160,140,173)),line('Status:',(270,160,310,173)),
             line('Priority:',(110,185,165,198)),line('Resolution:',(270,185,350,198)),
             line('Description',(110,215,190,228)),line('Repair the request handler',(110,235,510,250)),
             line('(a) Issue record',(245,283,365,296)),line('(b) Code change',(240,403,370,416))]
    assert check(objects,lines)['13']['findings'] == []


def test_unlabelled_grid_keeps_native_fragments_inside_shared_title_envelope():
    objects = [obj('figure',(x,y,x+175,y+120),role='chart_body')
               for x in (100,300) for y in (130,260)]
    objects.append(obj('figure_caption',(70,390,520,425),'Figure 9.1 Shared experiment'))
    assert check(objects,images=[(105,140,273,270),(225,131,320,142)])['13']['findings'] == []


def test_opening_parenthesis_is_optional_for_ordered_panel_labels():
    objects = [obj('figure',(100,100,500,220),role='image_body'),
               obj('figure',(100,270,500,400),role='image_body'),
               obj('figure_caption',(230,425,390,440),'Figure 9.2 Two stages')]
    lines = [line('a)',(102,102,112,113)),line('b)',(102,272,112,283))]
    assert check(objects,lines)['13']['findings'] == []


def test_bare_panel_letters_require_caption_enumeration():
    objects = [obj('figure',(100,100,500,220),role='image_body'),
               obj('figure',(100,270,500,400),role='image_body'),
               obj('figure_caption',(110,425,490,440),'Figure 9.3 Stages: (a) Input; (b) Output')]
    lines = [line('a',(102,102,112,113)),line('b',(102,272,112,283)),
             line('Figure 9.3 Stages: (a) Input; (b) Output',(110,425,490,440))]
    assert check(objects,lines)['13']['findings'] == []


def test_bare_axis_variables_without_panel_description_keep_independent_figures():
    objects = [obj('figure',(100,100,500,220),role='image_body'),
               obj('figure',(100,270,500,400),role='image_body'),
               obj('figure_caption',(230,425,390,440),'Figure 9.4 One model')]
    lines = [line('a',(102,102,112,113)),line('b',(102,272,112,283))]
    assert len(check(objects,lines)['13']['findings']) == 1


def test_caption_panel_ranges_cover_bare_letters_inside_merged_envelope():
    objects = [obj('figure',(100,100,490,410),role='chart_body'),
               obj('figure',(300,110,510,240),role='chart_body'),
               obj('figure_caption',(100,435,520,470),'Figure 9.5: (a)-(c) Cohorts; (d) Performance')]
    lines = [line(t,b) for t,b in [('a',(102,102,112,113)),('b',(302,112,312,123)),
                                  ('c',(110,260,120,271)),('d',(300,270,310,281)),
                                  ('Figure 9.5: (a)-(c) Cohorts; (d) Performance',(100,435,520,470))]]
    assert check(objects,lines)['13']['findings'] == []


def test_later_caption_cannot_declare_bare_letters_for_earlier_independent_figures():
    objects = [obj('figure',(100,100,500,220),role='image_body'),
               obj('figure',(100,270,500,400),role='image_body'),
               obj('figure_caption',(230,425,390,440),'Figure 9.4 One model'),
               obj('figure',(100,550,500,700),role='image_body'),
               obj('figure_caption',(100,725,520,740),'Figure 9.5 Other comparison: (a) Input; (b) Output')]
    lines = [line('a',(102,102,112,113)),line('b',(102,272,112,283)),
             line('Figure 9.5 Other comparison: (a) Input; (b) Output',(100,725,520,740))]
    assert len(check(objects,lines)['13']['findings']) == 1


def test_listing_reference_and_code_named_methods_keep_real_data_table():
    objects = [obj('table',(70,300,520,610),role='table_body')]
    lines = [line('Listing 8.2 shows how the methods below are implemented.',(90,270,510,285)),
             line('Method',(90,312,150,325)),line('Runtime (ms)',(370,312,465,325))]
    for y,method,value in [(350,'x = scan(data)','18'),(390,'y = index(data)','7'),(430,'z = cache(data)','3')]:
        lines += [line(method,(90,y,240,y+13)),line(value,(380,y,410,y+13))]
    assert len(check(objects,lines)['14']['findings']) == 1


def test_neighbouring_column_caption_cannot_declare_bare_panel_letters():
    objects = [obj('figure',(60,100,260,220),role='image_body'),
               obj('figure',(60,270,260,400),role='image_body'),
               obj('figure_caption',(80,440,240,455),'Figure 9.4 One model'),
               obj('figure',(320,100,540,400),role='image_body'),
               obj('figure_caption',(300,425,560,440),'Figure 9.5: (a) Input; (b) Output')]
    lines = [line('a',(62,102,72,113)),line('b',(62,272,72,283))]
    assert len(check(objects,lines)['13']['findings']) == 1


def test_below_panel_letter_overlapping_next_row_bbox_stays_with_upper_panel():
    objects = [obj('figure',(x,y,x+175,y+120),role='chart_body')
               for x in (100,300) for y in (100,228)]
    objects.append(obj('figure_caption',(220,380,390,395),'Figure 9.6 Comparison'))
    lines = [line(f'({tag}) Panel',(x+40,y+122,x+125,y+135))
             for x,y,tag in [(100,100,'a'),(300,100,'b'),(100,228,'c'),(300,228,'d')]]
    assert check(objects,lines)['13']['findings'] == []


def test_one_middle_letter_typo_in_regular_grid_is_still_one_captioned_figure():
    objects = [obj('figure',(x,y,x+180,y+100),role='chart_body')
               for y in (100,225,350) for x in (80,300)]
    objects.append(obj('figure_caption',(230,477,370,492),'Figure 9.7 Analysis'))
    lines = [line(f'({tag}) Result',(x+20,y+103,x+165,y+116))
             for (x,y),tag in zip([(x,y) for y in (100,225,350) for x in (80,300)],'abcddf')]
    assert check(objects,lines)['13']['findings'] == []


def test_restarted_letter_grid_keeps_a_truly_untitled_figure():
    objects = [obj('figure',(x,y,x+180,y+100),role='chart_body')
               for y in (100,225) for x in (80,300)]
    objects.append(obj('figure_caption',(230,350,370,365),'Figure 9.8 Second comparison'))
    lines = [line(f'({tag}) Result',(x+20,y+103,x+165,y+116))
             for (x,y),tag in zip([(x,y) for y in (100,225) for x in (80,300)],'abab')]
    assert len(check(objects,lines)['13']['findings']) >= 1


def test_detached_coloured_key_strip_above_labelled_composite_is_a_legend(tmp_path):
    import pymupdf
    path=tmp_path/'legend.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        for x,color,text in [(150,(1,.4,.1),'Measured Time'),(310,(.1,.5,1),'Model Time')]:
            page.draw_rect((x,175,x+20,187),color=color,fill=color)
            page.insert_text((x+25,185),text,fontsize=10)
        pdf.save(path)
    objects=[obj('figure',(100,205,500,560),role='chart_body'),
             obj('figure',(145,170,445,190),role='native_figure'),
             obj('figure_caption',(210,585,390,600),'Figure 9.9 Comparison')]
    lines=[line('(a) First',(120,355,230,368)),line('(b) Second',(320,355,430,368))]
    doc=PdfDocument(path,(PdfPage(1,600,840,tuple(lines)),))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]


def test_thin_independent_coloured_chart_above_composite_is_not_a_legend(tmp_path):
    import pymupdf
    path=tmp_path/'thin-chart.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        page.draw_line((145,188),(445,188),color=(0,0,0))
        for dy,color in [(0,(1,.4,.1)),(6,(.1,.5,1))]:
            page.draw_polyline([(155,184-dy),(210,176-dy),(310,181-dy),(430,169-dy)],color=color)
        pdf.save(path)
    objects=[obj('figure',(100,205,500,560),role='chart_body'),
             obj('figure',(145,160,445,190),role='native_figure'),
             obj('figure_caption',(210,585,390,600),'Figure 9.9 Comparison')]
    lines=[line('(a) First',(120,355,230,368)),line('(b) Second',(320,355,430,368))]
    doc=PdfDocument(path,(PdfPage(1,600,840,tuple(lines)),))
    assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings'])==1


def test_single_letter_typo_grid_cannot_cross_experiment_body_paragraph():
    objects = [obj('figure',(x,y,x+180,y+100),role='chart_body')
               for y in (100,245,390) for x in (80,300)]
    objects.append(obj('figure_caption',(230,517,370,532),'Figure 9.7 Analysis'))
    lines = [line(f'({tag}) Result',(x+20,y+103,x+165,y+116))
             for (x,y),tag in zip([(x,y) for y in (100,245,390) for x in (80,300)],'abcddf')]
    lines.append(line('The next experiment uses a separate dataset.',(80,219,480,237)))
    assert len(check(objects,lines)['13']['findings']) >= 1


def test_single_letter_typo_grid_cannot_cross_another_object_caption():
    objects = [obj('figure',(x,y,x+180,y+100),role='chart_body')
               for y in (100,245,390) for x in (80,300)]
    objects += [obj('figure_caption',(230,517,370,532),'Figure 9.7 Analysis'),
                obj('table_caption',(140,220,430,233),'Table 9.2 An independent comparison')]
    lines = [line(f'({tag}) Result',(x+20,y+103,x+165,y+116))
             for (x,y),tag in zip([(x,y) for y in (100,245,390) for x in (80,300)],'abcddf')]
    assert len(check(objects,lines)['13']['findings']) >= 1


def test_top_series_legend_cannot_cross_body_or_table_caption(tmp_path):
    import pymupdf
    path=tmp_path/'separated-legend.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        for x,color,text in [(150,(1,.4,.1),'Measured Time'),(310,(.1,.5,1),'Model Time')]:
            page.draw_rect((x,175,x+20,187),color=color,fill=color)
            page.insert_text((x+25,185),text,fontsize=10)
        page.insert_text((80,202),'The following experiment uses a separate dataset.',fontsize=10)
        pdf.save(path)
    for barrier in ('body','short_body','table_caption'):
        objects=[obj('figure',(100,205,500,560),role='chart_body'),
                 obj('figure',(145,170,445,190),role='native_figure'),
                 obj('figure_caption',(210,585,390,600),'Figure 9.9 Comparison')]
        lines=[line('(a) First',(120,355,230,368)),line('(b) Second',(320,355,430,368))]
        if barrier in {'body','short_body'}:
            lines.append(line('另一组实验结果如下。',(80,191,212,204)) if barrier=='short_body' else line('The following experiment uses a separate dataset.',(80,191,480,204)))
        else:
            objects.append(obj('table_caption',(140,191,460,204),'Table 9.3 A different experiment'))
        doc=PdfDocument(path,(PdfPage(1,600,840,tuple(lines)),))
        assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings'])==1


def test_short_chinese_sentence_separates_typo_grid_unless_inside_native_ink():
    objects = [obj('figure',(x,y,x+180,y+100),role='chart_body')
               for y in (100,245,390) for x in (80,300)]
    objects.append(obj('figure_caption',(230,517,370,532),'Figure 9.7 Analysis'))
    lines = [line(f'({tag}) Result',(x+20,y+103,x+165,y+116))
             for (x,y),tag in zip([(x,y) for y in (100,245,390) for x in (80,300)],'abcddf')]
    short_box=(80,219,212,231)
    lines.append(line('另一组实验结果如下。',short_box))
    for graphics,has_finding in [((),True),((short_box,),False)]:
        doc=PdfDocument(Path('short-boundary.pdf'),(PdfPage(1,600,840,tuple(lines),graphics=graphics),))
        findings=detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']
        assert bool(findings) is has_finding


def test_physical_raster_and_smaller_cloud_body_have_one_caption_owner():
    objects = [obj('figure',(160,155,390,350),role='image_body'),
               obj('figure_caption',(170,385,420,415),'Figure 11.1 Positioning diagram')]
    assert check(objects,images=[(110,140,450,370)])['13']['findings'] == []


def test_one_physical_raster_split_into_three_cloud_charts_has_one_owner():
    objects = [obj('figure',(x,200,x+140,350),role='chart_body') for x in (85,225,365)]
    objects.append(obj('figure_caption',(220,362,395,395),'Figure 11.2 Experiment results'))
    assert check(objects,images=[(86,199,508,353)])['13']['findings'] == []


def test_untitled_physical_raster_still_reports_once_after_cloud_deduplication():
    objects = [obj('figure',(x,200,x+140,350),role='chart_body') for x in (85,225,365)]
    assert len(check(objects,images=[(86,199,508,353)])['13']['findings']) == 1


def test_physical_raster_with_internal_caption_keeps_independent_missing_figure():
    objects = [obj('figure',(110,110,480,240),role='image_body'),
               obj('figure',(110,360,480,510),role='image_body'),
               obj('figure_caption',(220,270,390,290),'Figure 11.3 First result')]
    assert any(f['location']['bounding_rect']['y1'] == 360
               for f in check(objects,images=[(90,100,510,540)])['13']['findings'])


def test_native_envelope_without_single_raster_evidence_cannot_merge_cloud_figures():
    objects = [obj('figure',(100,100,280,250),role='image_body'),
               obj('figure',(320,100,500,250),role='image_body'),
               obj('figure',(80,80,520,270),role='native_figure'),
               obj('figure_caption',(330,280,480,295),'Figure 11.4 Right result')]
    assert any(f['location']['bounding_rect']['x1'] == 100
               for f in check(objects)['13']['findings'])


def test_single_raster_with_one_local_title_keeps_untitled_neighbour():
    objects = [obj('figure',(100,100,280,250),role='image_body'),
               obj('figure',(320,100,500,250),role='image_body'),
               obj('figure_caption',(330,280,480,295),'Figure 11.5 Right result')]
    assert any(f['location']['bounding_rect']['x1'] == 100
               for f in check(objects,images=[(80,80,520,270)])['13']['findings'])


def test_raster_carrier_of_two_captioned_figures_is_not_a_third_figure():
    objects = [obj('figure',(110,110,480,240),role='image_body'),
               obj('figure',(110,360,480,510),role='image_body'),
               obj('figure_caption',(220,270,390,290),'Figure 11.6 First result'),
               obj('figure_caption',(220,530,390,550),'Figure 11.7 Second result')]
    assert check(objects,images=[(90,100,510,570)])['13']['findings'] == []


def test_raster_carrier_with_internal_title_does_not_double_count_untitled_figure():
    objects = [obj('figure',(110,110,480,240),role='image_body'),
               obj('figure',(110,360,480,510),role='image_body'),
               obj('figure_caption',(220,270,390,290),'Figure 11.8 First result')]
    findings = check(objects,images=[(90,100,510,570)])['13']['findings']
    assert len(findings) == 1
    assert findings[0]['location']['bounding_rect']['y1'] == 360


def test_shared_axis_grid_is_resolved_before_unlabelled_columns_join():
    positions=[(x,y) for y in (100,204) for x in (100,300)]
    objects=[obj('figure',(x,y,x+180,y+100),role='chart_body') for x,y in positions]
    axes=[line('Scale Factor',(x+55,y+84,x+125,y+98)) for x,y in positions]
    objects.append(obj('figure_caption',(190,325,390,340),'Figure 12.1 Scalability analysis'))
    assert check(objects,axes)['13']['findings'] == []


def test_shared_axis_grid_with_different_last_row_count_has_one_total_caption():
    positions=[(x,y) for y in (100,203) for x in (140,250,360)]
    positions += [(x,306) for x in (80,190,300,410)]
    objects=[obj('figure',(x,y,x+100,y+100),role='chart_body') for x,y in positions]
    axes=[line('Time (s)',(x+25,y+84,x+75,y+98)) for x,y in positions]
    objects.append(obj('figure_caption',(110,425,490,442),'Figure 12.2 Comparison across wavelengths'))
    assert check(objects,axes)['13']['findings'] == []


def test_untitled_shared_axis_grid_remains_reported():
    positions=[(x,y) for y in (100,204) for x in (100,300)]
    objects=[obj('figure',(x,y,x+180,y+100),role='chart_body') for x,y in positions]
    axes=[line('Scale Factor',(x+55,y+84,x+125,y+98)) for x,y in positions]
    assert check(objects,axes)['13']['findings']


def test_shared_axis_rows_with_own_title_do_not_borrow_lower_total_title():
    positions=[(x,y) for y in (100,250) for x in (100,300)]
    objects=[obj('figure',(x,y,x+180,y+100),role='chart_body') for x,y in positions]
    axes=[line('Scale Factor',(x+55,y+84,x+125,y+98)) for x,y in positions]
    objects += [obj('figure_caption',(320,215,470,230),'Figure 12.3 Top right'),
                obj('figure_caption',(190,365,390,380),'Figure 12.4 Lower row')]
    assert any(f['location']['bounding_rect']['x1'] == 100
               and f['location']['bounding_rect']['y1'] == 100
               for f in check(objects,axes)['13']['findings'])
