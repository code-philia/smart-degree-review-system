"""Recover printed English type words broken across adjacent body rows."""
from dataclasses import replace
import re

from .numbering import FIGURE_REFERENCE, TABLE_REFERENCE
from .usage_text_cache import normalize_text
from .bibliography_scope_resume import _native_glyphs
from .usage_paragraphs import _intervening_content,span_anchor


def _complete_native_ink(line,document):
    if _native_glyphs(line):return line
    if line.source!='native':return None
    # A printed ligature may normalize to two letters while an old parser
    # checkpoint keeps the previous offsets. Reconstruct only this candidate
    # row from actual PDF characters; the shared index remains untouched.
    try:
        import pymupdf
        with pymupdf.open(document.path) as pdf:
            possibilities=[]
            for block in pdf[line.page_number-1].get_text('rawdict')['blocks']:
                if block.get('type')!=0:continue
                for row in block['lines']:
                    if tuple(row['dir'])!=(1.0,0.0):continue
                    chars=[char for span in row['spans'] for char in span['chars']
                           if line.bbox[0]-.5<=char['bbox'][0] and char['bbox'][2]<=line.bbox[2]+.5
                           and line.bbox[1]-.5<=char['bbox'][1] and char['bbox'][3]<=line.bbox[3]+.5]
                    text='';regions=[]
                    previous=None
                    for char in chars:
                        value=normalize_text(char['c']);start=len(text);text+=value
                        box=tuple(char['bbox'])
                        if (box[2]==box[0] and previous and char['c'] in {'i','l'} and previous['c']=='f'
                                and previous['bbox'][2]>previous['bbox'][0]
                                and abs(box[0]-previous['bbox'][2])<=.1
                                and abs(box[1]-previous['bbox'][1])<=.1
                                and abs(box[3]-previous['bbox'][3])<=.1):
                            # MuPDF can expose the second letter of a printed
                            # fi/fl ligature with zero advance at the first
                            # letter's end. Both letters own that original
                            # compound glyph, never an invented rectangle.
                            box=tuple(previous['bbox'])
                        regions.append((start,len(text),box));previous=char
                    if text==normalize_text(line.text):
                        possibilities.append(replace(line,text=text,text_regions=tuple(regions),reference_regions=()))
        return possibilities[0] if len(possibilities)==1 and _native_glyphs(possibilities[0]) else None
    except (OSError,RuntimeError,ValueError,ImportError,IndexError):return None


def _mixed_body_weight(line,document):
    if not line.bold:return True
    # The frozen parser marks a complete row bold when one inline phrase is
    # emphasized. The original font spans must prove ordinary prose ink.
    try:
        import pymupdf
        with pymupdf.open(document.path) as pdf:
            spans=[s for block in pdf[line.page_number-1].get_text('dict')['blocks'] if block.get('type')==0
                   for row in block['lines'] for s in row['spans']
                   if line.bbox[0]-1<=s['bbox'][0] and s['bbox'][2]<=line.bbox[2]+1
                   and line.bbox[1]-1<=s['bbox'][1] and s['bbox'][3]<=line.bbox[3]+1
                   and line.font_size and abs(s['size']-line.font_size)<=.2]
        spans.sort(key=lambda s:s['bbox'][0])
        compact=lambda value:re.sub(r'\s+','',normalize_text(value))
        if compact(''.join(s['text'] for s in spans))!=compact(line.text):return False
        letters=lambda value:len(re.findall(r'[A-Za-z\u4e00-\u9fff]',value))
        total=sum(letters(s['text']) for s in spans)
        normal=sum(letters(s['text']) for s in spans if not s['flags']&16)
        return total>=30 and normal>=total*.5
    except (OSError,RuntimeError,ValueError,ImportError,IndexError):return False


def wrapped_native_references(document,pages,fonts,protected,directories,zone,prose_shape,uses,graph_symbols):
    words={'figure':'figure','figures':'figure','table':'table','tables':'table'}
    answer=[]
    excluded={'figure','table','figure_caption','table_caption','header','footer','equation'}
    for page in document.pages:
        ordered=sorted(page.lines,key=lambda row:(row.bbox[1],row.bbox[0]))
        for first,second in zip(ordered,ordered[1:]):
            prefix=re.search(r'(?<![A-Za-z0-9_./\\])([A-Za-z]+)-\s*$',normalize_text(first.text))
            if prefix is None:continue
            head=prefix.group(1).casefold()
            possibilities=[(word,kind,word[len(head):]) for word,kind in words.items()
                           if word.startswith(head) and 0<len(head)<len(word)]
            for word,kind,tail in possibilities:
                suffix=re.match(re.escape(tail)+r'(?=\s|\()',normalize_text(second.text),re.I)
                if suffix is None:continue
                complete_first=_complete_native_ink(first,document)
                complete_second=_complete_native_ink(second,document)
                if complete_first is None or complete_second is None:continue
                first,second=complete_first,complete_second
                if any((row.page_number,row.bbox) in protected|directories or row.role in excluded
                       or not _native_glyphs(row) or not _mixed_body_weight(row,document)
                       or not prose_shape(replace(row,bold=False),page,fonts[page.number])
                       or any(b[0]-.5<=row.bbox[0] and b[1]-.5<=row.bbox[1]
                              and row.bbox[2]<=b[2]+.5 and row.bbox[3]<=b[3]+.5
                              for b in (*page.images,*page.tables,*page.graphics))
                       for row in (first,second)):continue
                scope,epoch=zone(first)
                if scope=='_nonbody' or zone(second)!=(scope,epoch):continue
                if (first.page_number!=second.page_number or not first.font_size or not second.font_size
                        or abs(first.font_size-second.font_size)>.2
                        or first.bbox[2]-first.bbox[0]<first.page_width*.6
                        or not 0<=second.bbox[1]-first.bbox[3]<=first.font_size*1.3
                        or abs(first.bbox[0]-second.bbox[0])>first.font_size*2.5
                        or _intervening_content(first,second,page)):continue
                canonical=normalize_text(first.text[:prefix.start(1)])+word+normalize_text(second.text[suffix.end():])
                pattern=FIGURE_REFERENCE if kind=='figure' else TABLE_REFERENCE
                start=len(normalize_text(first.text[:prefix.start(1)]))
                match=next((m for m in pattern.finditer(canonical) if m.start()==start),None)
                if match is None:continue
                # The temporary semantic string is used only for the shared
                # literal/external parser. Reference ink stays on the actual
                # number in the second printed row.
                view=replace(second,text=canonical)
                for reference in uses(view,kind,scope,graph_symbols if kind=='figure' else None):
                    if reference.number!=match.group('number').upper().replace('-','.'):continue
                    shift=suffix.end()-start-len(word)
                    anchor=span_anchor(second,match.start('number')+shift,match.end('number')+shift)
                    answer.append((kind,replace(reference,line=anchor),(scope,epoch),first))
    return answer
