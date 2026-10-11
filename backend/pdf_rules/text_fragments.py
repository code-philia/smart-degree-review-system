"""Reconstruct a reference split on one row or across adjacent prose lines."""
from dataclasses import replace
import re
from .numbering import LABEL, FIGURE_REFERENCE_LABEL, normalize_text

PARTIAL = re.compile(r"(?:图|表(?:格)?|Figure|Fig\.?|Table)\s*[(（]?\s*(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*(?:[,，、和及与]\s*(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*)*[.\-,，、和及与至到]\s*$", re.I)
PREFIX = re.compile(r'(?:图(?:所示?)?|表(?:格)?|Figure|Fig\.?|Table|附录|Appendix)\s*$', re.I)
NUMBER = re.compile(rf'^\s*(?:{LABEL}|[A-Z](?![A-Za-z]))', re.I)
FIGURE_NUMBER = re.compile(rf'^\s*{FIGURE_REFERENCE_LABEL}',re.I)
SHOWN_NUMBER = re.compile(rf'^\s*示\s*{FIGURE_REFERENCE_LABEL}',re.I)
TABLE_WORD_NUMBER = re.compile(rf'^\s*(?:格\s*)?[(（]?\s*{FIGURE_REFERENCE_LABEL}',re.I)


def merge_reference_fragments(lines, cell_borders=()):
    result = list(lines)
    consumed = set()
    for i, left in enumerate(result):
        if i in consumed or not (PREFIX.search(normalize_text(left.text)) or PARTIAL.search(normalize_text(left.text))):
            continue
        number_pattern = FIGURE_NUMBER if re.search(r"(?:图|表(?:格)?|Figure|Fig\.?|Table)\s*$",normalize_text(left.text),re.I) else NUMBER
        if re.search(r'表\s*$',normalize_text(left.text)):number_pattern=TABLE_WORD_NUMBER
        if re.search(r'图所\s*$',normalize_text(left.text)):number_pattern=SHOWN_NUMBER
        candidates = []
        for j, right in enumerate(result):
            if j == i or j in consumed or left.page_number != right.page_number or left.source != right.source:
                continue
            if not number_pattern.match(normalize_text(right.text)):
                continue
            height = min(left.bbox[3]-left.bbox[1], right.bbox[3]-right.bbox[1])
            gap = right.bbox[0]-left.bbox[2]
            overlap = min(left.bbox[3], right.bbox[3])-max(left.bbox[1], right.bbox[1])
            same_row = height > 0 and 0 <= gap <= height*2 and overlap >= height*.6
            # A soft wrap must be ordinary prose at a column margin, not a
            # standalone caption prefix or a number from another row/cell.
            vertical_gap = right.bbox[1] - left.bbox[3]
            partial = PARTIAL.search(normalize_text(left.text))
            prefix = partial or PREFIX.search(normalize_text(left.text))
            wrapped = (height > 0 and 0 <= vertical_gap <= height*1.3
                       and abs(right.bbox[0]-left.bbox[0]) <= height*3
                       and left.bbox[2]-left.bbox[0] >= left.page_width*.45
                       and prefix.start() >= 3
                       and (len(normalize_text(right.text)[number_pattern.match(normalize_text(right.text)).end():].strip()) >= 2
                            or re.fullmatch(r'[)）\]：:，,。.;；!?！？]+',
                                normalize_text(right.text)[number_pattern.match(normalize_text(right.text)).end():].strip()))
                       and not any(k not in {i,j} and line.page_number == left.page_number
                                   and left.bbox[3] < line.bbox[1] < right.bbox[1]
                                   and max(line.bbox[0],left.bbox[0]) < min(line.bbox[2],left.bbox[2])
                                   for k,line in enumerate(result)))
            # Numbered executable rows are separate instructions. A Chinese
            # comment ending in 图 cannot borrow the next statement's row ID.
            def numbered_statement(text):
                normalized=normalize_text(text)
                return (bool(re.match(r'^\s*\d+[.:]\s+',normalized))
                        and bool(re.search(r'←|:=|\b(?:for|while|if|return)\b',normalized,re.I)))
            if wrapped and numbered_statement(left.text) and numbered_statement(right.text):
                continue
            if not (same_row or wrapped):
                continue
            if wrapped and any(min(left.bbox[0],right.bbox[0]) <= x <= max(left.bbox[2],right.bbox[2])
                               and y1 <= left.bbox[1] and y2 >= right.bbox[3]
                               for x,y1,y2 in cell_borders):
                continue
            # A real citation may be inside one cell. Only reject a join
            # when a visible cell border lies between the two fragments.
            row_top = max(left.bbox[1], right.bbox[1])
            row_bottom = min(left.bbox[3], right.bbox[3])
            if any(left.bbox[2] <= x <= right.bbox[0]
                   and y1 <= row_top and y2 >= row_bottom
                   for x, y1, y2 in cell_borders):
                continue
            candidates.append((int(not same_row), gap if same_row else vertical_gap, j, right))
        if candidates:
            _, _, j, right = min(candidates, key=lambda candidate: candidate[:2])
            separator = '' if number_pattern is SHOWN_NUMBER or PARTIAL.search(normalize_text(left.text)) or (number_pattern is TABLE_WORD_NUMBER and normalize_text(right.text).lstrip().startswith('格')) else ' '
            start = len(normalize_text(left.text)) + len(separator)
            match = number_pattern.match(normalize_text(right.text))
            number_start = match.start('number') if match.groupdict().get('number') else match.start()
            number_end = match.end('number') if match.groupdict().get('number') else match.end()
            boxes = [box for a, b, box in right.text_regions if a < number_end and b > number_start]
            focus = ((min(box[0] for box in boxes), min(box[1] for box in boxes),
                      max(box[2] for box in boxes), max(box[3] for box in boxes)) if boxes else right.bbox)
            result[i] = replace(left, text=left.text+separator+right.text,
                bbox=(min(left.bbox[0],right.bbox[0]), min(left.bbox[1],right.bbox[1]),
                      max(left.bbox[2],right.bbox[2]), max(left.bbox[3],right.bbox[3])),
                text_regions=left.text_regions+tuple((a+start,b+start,box) for a,b,box in right.text_regions),
                reference_regions=(left.reference_regions
                    +((start+number_start,start+number_end,focus),)
                    +tuple((a+start,b+start,box) for a,b,box in right.reference_regions)))
            consumed.add(j)
    joined = tuple(line for i, line in enumerate(result) if i not in consumed)
    # A sentence can contain several split references. Each pass consumes
    # fragments, so subsequent passes terminate when every join is resolved.
    return merge_reference_fragments(joined, cell_borders) if consumed else joined
