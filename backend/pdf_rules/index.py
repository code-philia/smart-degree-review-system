import re
from dataclasses import replace
from .reference_context import local_reference, defined_graph_symbols, graph_variable_use
from .reference_groups import reference_matches
from .caption_context import contextual_caption,caption_region_lines,caption_number_fragment
from .model import DocumentIndex, Label, PdfDocument
from .numbering import (
    APPENDIX_HEADING, APPENDIX_QUALIFIER, APPENDIX_REFERENCE, FIGURE_CAPTION, FIGURE_REFERENCE,
    TABLE_CAPTION, TABLE_REFERENCE, is_appendix_heading, is_toc_line, normalize_label, normalize_text, caption_match, toc_line_keys,
)


def _reference_label(match, text, line, scope):
    number = normalize_label(match.group("number"))
    prefix = text[max(0, match.start() - 16):match.start()]
    qualifier = APPENDIX_QUALIFIER.search(prefix)
    target_scope = (normalize_label(qualifier.group("number")) if qualifier else
                    number[0] if len(number) > 1 and number[1] == "." and number[0].isalpha()
                    else None)
    # Split-reference reconstruction retains original character rectangles.
    # Keep the full sentence as context, but highlight its actual target number.
    for start, end, box in line.reference_regions:
        if start <= match.start("number") and match.end("number") <= end:
            line = replace(line, bbox=box)
            break
    else:
        boxes = [box for start, end, box in line.text_regions
                 if start < match.end("number") and end > match.start("number")]
        if boxes:
            line = replace(line, bbox=(min(b[0] for b in boxes), min(b[1] for b in boxes),
                                      max(b[2] for b in boxes), max(b[3] for b in boxes)))
    return Label(number, line, scope, target_scope)


def build_index(document: PdfDocument, layout_objects=None) -> DocumentIndex:
    index = DocumentIndex(document)
    graph_symbols=defined_graph_symbols(document)
    scope = "body"
    implicit_lines=[]
    directory_lines = toc_line_keys(document)
    pages = {p.number:p for p in document.pages}
    from .caption_rules import _matches
    from .mineru_layout import LayoutObject
    captions = [LayoutObject("figure_caption",l.page_number,l.bbox,l.text,l.page_width,l.page_height)
                for l in document.lines if contextual_caption(l,pages[l.page_number],"figure",layout_objects)
                and (l.page_number,l.bbox) not in directory_lines]
    from .graphic_context import native_figure_regions, detached_from_native_figure
    native_regions = native_figure_regions(document,directory_lines)
    figure_regions = [o for o in (*list(layout_objects or ()),*native_regions) if o.kind=="figure"
                      and any(_matches(o,c) for c in captions)]
    caption_regions=caption_region_lines(document,layout_objects)
    for line in document.lines:
        text = normalize_text(line.text)
        # Directory entries cannot open document sections or appendix scopes.
        if is_toc_line(text) or (line.page_number, line.bbox) in directory_lines:
            continue
        heading = APPENDIX_HEADING.search(text)
        if heading and is_appendix_heading(text, heading):
            scope = normalize_label(heading.group("number"))
            index.appendices.append(Label(scope, line, scope))
            continue

        if caption_number_fragment(line,pages[line.page_number]):
            continue
        figure_caption = contextual_caption(line, pages[line.page_number], "figure",layout_objects)
        table_caption = contextual_caption(line, pages[line.page_number], "table",layout_objects)
        if figure_caption:
            index.figures.append(Label(normalize_label(figure_caption.group("number")), line, scope))
        if table_caption:
            index.tables.append(Label(normalize_label(table_caption.group("number")), line, scope))

        inside_figure = not figure_caption and not table_caption and any(
            obj.kind == "figure" and obj.page_number == line.page_number
            and obj.bbox[0] <= line.bbox[0] and obj.bbox[2] >= line.bbox[2]
            and obj.bbox[1] <= line.bbox[1] and obj.bbox[3] >= line.bbox[3]
            and not detached_from_native_figure(line,pages[line.page_number],obj,native_regions)
            for obj in figure_regions)

        inside_caption=bool(figure_caption or table_caption or (line.page_number,line.bbox) in caption_regions)
        if not inside_caption and not inside_figure:
            implicit_lines.append((line,scope))

        # A caption's own number is not a citation. References later in its
        # title still count (for example, "图 2.1 与图 1.1 对比").
        figure_start = figure_caption.end("number") if figure_caption else 0
        table_start = table_caption.end("number") if table_caption else 0
        for match in reference_matches(FIGURE_REFERENCE,text):
            if (figure_caption or table_caption) and match.start("number") < max(figure_start,table_start):
                continue
            if not local_reference(text, match) or graph_variable_use(text,match,graph_symbols):continue
            if inside_figure or inside_caption:
                if inside_caption or explicit_graphic_citation(text,match):index.graphic_figure_refs.append(_reference_label(match,text,line,scope))
                continue
            # Ordinary prose is parsed once after wrap reconstruction below.
        for match in reference_matches(TABLE_REFERENCE,text):
            if (figure_caption or table_caption) and match.start("number") < max(figure_start,table_start):
                continue
            if not local_reference(text, match):continue
            if inside_figure or inside_caption:
                if inside_caption or explicit_graphic_citation(text,match):index.graphic_table_refs.append(_reference_label(match,text,line,scope))
                continue
            # Ordinary prose is parsed once after wrap reconstruction below.
        for match in APPENDIX_REFERENCE.finditer(text):
            if local_reference(text, match):
                index.appendix_refs.append(Label(normalize_label(match.group("number")), line, scope))
    # Citation inheritance operates on prose, not physical PDF lines. Only
    # eligible body lines are joined; directory entries, captions, graphic
    # content, pages and appendix scopes remain separate. Parsing the body
    # here (rather than both before and after joining) preserves distinct ink
    # occurrences while preventing duplicate missing-target alarms.
    from .usage_paragraphs import usage_paragraphs
    prose = usage_paragraphs(implicit_lines,document)
    for line, scope in prose:
        text = normalize_text(line.text)
        for match in reference_matches(FIGURE_REFERENCE, text):
            if local_reference(text, match) and not graph_variable_use(text, match, graph_symbols):
                index.figure_refs.append(_reference_label(match, text, line, scope))
        for match in reference_matches(TABLE_REFERENCE, text):
            if local_reference(text, match):
                index.table_refs.append(_reference_label(match, text, line, scope))
    from .implicit_references import add_implicit_references
    add_implicit_references(index,prose,layout_objects or figure_regions,paragraphs_restored=True)
    from .cross_page_typed_references import recover_cross_page_typed_references
    recover_cross_page_typed_references(index,layout_objects or (),eligible_lines=implicit_lines)
    from .typed_panel_references import bind_source_panel_references
    bind_source_panel_references(index,layout_objects or ())
    return index


def explicit_graphic_citation(text,match):
    """Usage may be explicitly stated in another figure's algorithm text.

    Do not run missing-target rule 11 on graphic labels. Only prose pointing
    to another object can establish usage for rules 15/16.
    """
    before=text[:match.start()];after=text[match.end():]
    return bool(re.search(r'(?:参见|详见|参照|见|同|如|摘自|引自)\s*$',before)
                or re.match(r'\s*(?:所示|所述|展示了|显示了)',after))
