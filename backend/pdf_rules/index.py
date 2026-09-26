from .model import DocumentIndex, Label, PdfDocument
from .numbering import (
    APPENDIX_HEADING, APPENDIX_QUALIFIER, APPENDIX_REFERENCE, FIGURE_CAPTION, FIGURE_REFERENCE,
    TABLE_CAPTION, TABLE_REFERENCE, is_appendix_heading, is_toc_line, normalize_label, normalize_text,
)


def _reference_label(match, text, line, scope):
    number = normalize_label(match.group("number"))
    prefix = text[max(0, match.start() - 16):match.start()]
    qualifier = APPENDIX_QUALIFIER.search(prefix)
    target_scope = (normalize_label(qualifier.group("number")) if qualifier else
                    number[0] if len(number) > 1 and number[1] == "." and number[0].isalpha()
                    else None)
    return Label(number, line, scope, target_scope)


def build_index(document: PdfDocument, layout_objects=None) -> DocumentIndex:
    index = DocumentIndex(document)
    scope = "body"
    for line in document.lines:
        text = normalize_text(line.text)
        heading = APPENDIX_HEADING.search(text)
        if heading and is_appendix_heading(text, heading):
            scope = normalize_label(heading.group("number"))
            index.appendices.append(Label(scope, line, scope))
            continue
        if is_toc_line(text):
            continue

        figure_caption = FIGURE_CAPTION.search(text)
        table_caption = TABLE_CAPTION.search(text)
        if figure_caption:
            index.figures.append(Label(normalize_label(figure_caption.group("number")), line, scope))
        if table_caption:
            index.tables.append(Label(normalize_label(table_caption.group("number")), line, scope))

        # A caption's own number is not a citation. References later in its
        # title still count (for example, "图 2.1 与图 1.1 对比").
        figure_start = figure_caption.end("number") if figure_caption else 0
        table_start = table_caption.end("number") if table_caption else 0
        for match in FIGURE_REFERENCE.finditer(text):
            if figure_caption and match.start() < figure_start:
                continue
            index.figure_refs.append(_reference_label(match, text, line, scope))
        for match in TABLE_REFERENCE.finditer(text):
            if table_caption and match.start() < table_start:
                continue
            index.table_refs.append(_reference_label(match, text, line, scope))
        for match in APPENDIX_REFERENCE.finditer(text):
            index.appendix_refs.append(Label(normalize_label(match.group("number")), line, scope))
    return index
