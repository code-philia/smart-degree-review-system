"""PDF observations become a typed tree without rewriting the source document."""
from collections import Counter
import hashlib
from pathlib import Path
import re
import statistics

import pymupdf

from .citations import attach_citations
from .contracts import SCHEMA_VERSION, MODEL_VERSION, validate_ir
from .llm import ModelError

FRONTEND_VERSION='pdf-source-frontend/1.1'
BIB_HEADING=re.compile(r'^(?:参考文献|參考文獻|References|Bibliography)\s*$',re.I)
ENTRY=re.compile(r'^\s*(?:[\[［](\d{1,4})[\]］]|(\d{1,4})[.、．])\s*')
NUMBERED_HEADING=re.compile(r'^(?:(第[一二三四五六七八九十百\d]+章)\s*|((?:\d+\.)*\d+)\s+)(\S.{0,65})$')
BACK_HEADING=re.compile(r'^(?:致\s*谢|Acknowledg(?:e)?ments|附录\s*[A-Z一二三\d]?|Appendix\s*[A-Z]?|攻读.*成果|个人简历)\s*$',re.I)


def _box(chars,width,height):
    b=[min(c['bbox'][0] for c in chars),min(c['bbox'][1] for c in chars),max(c['bbox'][2] for c in chars),max(c['bbox'][3] for c in chars)]
    return [max(0,min(width,b[0])),max(0,min(height,b[1])),max(0,min(width,b[2])),max(0,min(height,b[3]))]


def _observe(pdf):
    pages=[]
    with pymupdf.open(pdf) as document:
        for index,page in enumerate(document):
            rotation=page.rotation
            label=page.get_label() or None
            page.set_rotation(0)
            width,height=float(page.rect.width),float(page.rect.height)
            lines=[]
            data=page.get_text('rawdict',sort=True,flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
            for bi,block in enumerate(data['blocks']):
                if block.get('type')!=0:continue
                for li,line in enumerate(block.get('lines',[])):
                    chars=[];offset=0
                    for span in line.get('spans',[]):
                        for char in span.get('chars',[]):
                            value=char['c'];end=offset+len(value)
                            chars.append({'text':value,'start':offset,'end':end,'bbox':list(char['bbox']),
                                          'size':float(span['size']),'font':span['font'],'flags':span['flags']})
                            offset=end
                    if not chars or not ''.join(c['text'] for c in chars).strip():continue
                    lines.append({'id':f'p{index}-b{bi}-l{li}','text':''.join(c['text'] for c in chars),
                        'bbox':_box(chars,width,height),'chars':chars,'block_id':bi,
                        'font_size':statistics.median(c['size'] for c in chars),
                        'direction':list(line.get('dir',(1,0)))})
            images=[]
            for image in page.get_image_info():
                rect=pymupdf.Rect(image['bbox']) & page.rect
                if not rect.is_empty:images.append(list(rect))
            pages.append({'page_index':index,'width':width,'height':height,'rotation':rotation,
                'printed_page_label':label,'lines':lines,'images':images,'text_status':'observed' if lines else 'unknown'})
    return pages



def _is_bibliography_heading(text):
    return bool(BIB_HEADING.fullmatch(text.strip()) or re.sub(r'\s+','',text) in {'参考文献','參考文獻'})

def _bibliography_heading(pages,client,*,observations=None):
    flat=[(page,line) for page in pages for line in page['lines']];candidates=[]
    for index,(page,line) in enumerate(flat):
        if not _is_bibliography_heading(line['text']):continue
        following=[other['text'] for _,other in flat[index+1:index+13]]
        markers=[ENTRY.match(t.strip()) for t in following];numbers=[int(m.group(1) or m.group(2)) for m in markers if m]
        candidates.append({'id':line['id'],'page_index':page['page_index'],'text':line['text'],'font_size':line['font_size'],
            'preceding':[other['text'] for _,other in flat[max(0,index-3):index]],'following':following,'first_numeric_key':numbers[0] if numbers else None})
    if not candidates:return None,'not_found'
    if len(candidates)>1 and client is not None:
        try:
            answer=client.complete_json('bibliography-boundary/1.0',
                'Identify the start heading of the MAIN actual bibliography from the supplied source candidates. Exclude table-of-contents labels, diagram labels, prompt examples and running headers. Use following bibliographic entries and page position. Return heading_id (one exact supplied ID, or null if unclear) and reason. Do not invent source IDs.',
                {'page_count':len(pages),'candidates':candidates},1200)
        except ModelError as error:
            if observations is not None:
                observations.append({'task':'bibliography-boundary/1.0','status':'unavailable',
                    'error_type':type(error).__name__,'error_message':str(error),
                    'candidate_line_ids':[candidate['id'] for candidate in candidates],
                    'decision':'unlocated; no candidate inferred after optional model failure'})
            return None,'model_error_unlocated'
        if answer.get('heading_id') in {c['id'] for c in candidates}:return answer['heading_id'],'model_selected_source_heading'
        if answer.get('heading_id') is not None:raise ValueError('bibliography selector returned an unknown source line')
    # Main bibliography commonly starts at key 1; later diagram labels and running headers do not.
    candidates.sort(key=lambda c:(c['first_numeric_key']==1,c['first_numeric_key'] is not None,c['font_size'],c['page_index']),reverse=True)
    return candidates[0]['id'],'structural_candidate_unverified'

def build_paper(pdf: Path, *, client=None, layout_cache=None) -> dict:
    pdf=Path(pdf).resolve()
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    pages=_observe(pdf)
    bibliography_observations=[]
    bibliography_heading,bibliography_method=_bibliography_heading(pages,client,observations=bibliography_observations)
    nodes=[];by_id={}
    def add(kind,text,parent,attrs=None,lines=None,node_id=None):
        nid=node_id or 'n'+str(len(nodes))
        provenance=[];offset=0
        for page,line in lines or []:
            if provenance:offset+=1
            provenance.append({'kind':'source','source_id':'pdf','page_index':page['page_index'],
                'printed_page_label':page['printed_page_label'],'bbox':list(line['bbox']),
                'coordinate_system':'unrotated_top_left_points','rotation':page['rotation'],
                'line_id':line['id'],'text_offsets':[0,len(line['text'])],
                'node_text_start':offset,'node_text_end':offset+len(line['text'])})
            offset+=len(line['text'])
        node={'id':nid,'kind':kind,'text':text,'children':[],'attrs':attrs or {},'provenance':provenance}
        nodes.append(node);by_id[nid]=node
        if parent:by_id[parent]['children'].append(nid)
        return nid
    add('Paper',None,None,node_id='paper')
    add('FrontMatter',None,'paper',node_id='front')
    add('Body',None,'paper',node_id='body')
    add('BackMatter',None,'paper',node_id='back')
    top_bottom=Counter()
    for page in pages:
        for text in {line['text'].strip() for line in page['lines'] if line['bbox'][1]<50 or line['bbox'][3]>page['height']-35}:
            top_bottom[text]+=1
    all_sizes=[line['font_size'] for page in pages for line in page['lines']]
    normal=statistics.median(all_sizes) if all_sizes else 12
    bibliography=None;current_entry=None;section_stack=[];mode='front';paragraph=None;previous_line=None;entry_counter=0
    title_added=False
    def append_line(nid,page,line):
        node=by_id[nid];offset=len(node['text'])+1
        node['text']+='\n'+line['text']
        node['provenance'].append({'kind':'source','source_id':'pdf','page_index':page['page_index'],
            'printed_page_label':page['printed_page_label'],'bbox':list(line['bbox']),
            'coordinate_system':'unrotated_top_left_points','rotation':page['rotation'],
            'line_id':line['id'],'text_offsets':[0,len(line['text'])],
            'node_text_start':offset,'node_text_end':offset+len(line['text'])})
    for page in pages:
        for line in page['lines']:
            text=line['text'].strip()
            margin=line['bbox'][1]<50 or line['bbox'][3]>page['height']-35
            if margin and top_bottom[text]>=2:
                add('UnknownBlock',line['text'],'paper',{'role':'running_header' if line['bbox'][1]<50 else 'running_footer','reason':'repeated page margin'},[(page,line)])
                continue
            if margin and re.fullmatch(r'[ivxlcdmIVXLCDM\d]+',text):
                add('UnknownBlock',line['text'],'paper',{'role':'page_number','reason':'page margin locator'},[(page,line)])
                continue
            if line['id']==bibliography_heading:
                if bibliography is None:bibliography=add('Bibliography',None,'back',{'bibliography_kind':'cited_works'},node_id='bibliography')
                add('Heading',line['text'],bibliography,lines=[(page,line)])
                mode='bibliography';paragraph=None;current_entry=None;previous_line=None;continue
            if BACK_HEADING.fullmatch(text):
                mode='back';paragraph=None;current_entry=None
                kind='Appendix' if re.match(r'附录|Appendix',text,re.I) else 'Acknowledgements' if re.match(r'致|Ack',text,re.I) else 'Biography'
                section_stack=[(1,add(kind,None,'back'))]
                add('Heading',line['text'],section_stack[-1][1],lines=[(page,line)])
                previous_line=None;continue
            if mode=='bibliography':
                marker=ENTRY.match(text)
                starts_author=bool(re.match(r'^[A-Za-z\u4e00-\u9fff]',text) and re.search(r'\b(?:18|19|20)\d{2}\b',text) and
                    (current_entry is None or previous_line is None or
                     (page['page_index']==previous_line[0]['page_index'] and line['bbox'][1]-previous_line[1]['bbox'][3]>normal*1.3)))
                if marker or current_entry is None or starts_author:
                    entry_counter+=1
                    key=(marker.group(1) or marker.group(2)) if marker else 'author-year-'+str(entry_counter)
                    current_entry=add('BibliographyEntry',line['text'],bibliography,{'key':key},[(page,line)])
                else:append_line(current_entry,page,line)
                previous_line=(page,line);continue
            heading=NUMBERED_HEADING.fullmatch(text)
            named_heading=bool(len(text)<70 and line['font_size']>=normal*1.22 and not re.search(r'[。.!?]$',text))
            if mode=='front' and not title_added and not heading and not re.fullmatch(r'Abstract|摘要|目录|Contents',text,re.I):
                add('Title',line['text'],'front',lines=[(page,line)]);title_added=True;previous_line=None;continue
            if re.fullmatch(r'Abstract|摘要',text,re.I):
                section_stack=[(1,add('Abstract',None,'front'))];mode='abstract';paragraph=None
                add('Heading',line['text'],section_stack[-1][1],lines=[(page,line)]);previous_line=None;continue
            if re.fullmatch(r'Contents|目录',text,re.I):
                section_stack=[(1,add('ToC',None,'front'))];mode='toc';paragraph=None
                add('Heading',line['text'],section_stack[-1][1],lines=[(page,line)]);previous_line=None;continue
            if heading or (named_heading and mode not in {'toc','abstract'}):
                level=1 if not heading or heading.group(1) else heading.group(2).count('.')+1
                number=(heading.group(1) or heading.group(2)) if heading else ''
                while section_stack and section_stack[-1][0]>=level:section_stack.pop()
                parent=section_stack[-1][1] if section_stack else 'body'
                sid=add('Section',None,parent,{'number':number,'level':level})
                section_stack.append((level,sid));mode='body';paragraph=None
                add('Heading',line['text'],sid,{'number':number,'level':level},[(page,line)])
                previous_line=None;continue
            parent=section_stack[-1][1] if section_stack else 'body'
            caption=re.match(r'^(?:图|表|Figure\s+|Fig\.\s*|Table\s+)([A-Za-z]?\d+(?:[.．-]\d+)*)\s*',text,re.I)
            if caption:
                parent_object=add('Table' if re.match(r'表|Table',text,re.I) else 'Figure',None,parent,{'label':caption.group(1)})
                add('Caption',line['text'],parent_object,{'label':caption.group(1)},[(page,line)])
                paragraph=None;previous_line=None;continue
            can_join=paragraph is not None and previous_line is not None and page['page_index']==previous_line[0]['page_index'] and \
                0<=line['bbox'][1]-previous_line[1]['bbox'][3]<=normal*1.1 and abs(line['bbox'][0]-previous_line[1]['bbox'][0])<normal*3
            if can_join:append_line(paragraph,page,line)
            else:paragraph=add('ToCEntry' if mode=='toc' else 'Paragraph',line['text'],parent,lines=[(page,line)])
            previous_line=(page,line)
    readable=all(page['lines'] for page in pages) and bool(pages)
    ids=[line['id'] for page in pages for line in page['lines']]
    # A protocol completion is not a claim of perfect extraction; ambiguity is explicit.
    complete={'status':'complete','protocol':FRONTEND_VERSION,'evidence_ids':ids[:1]}
    partial={'status':'partial','reason':'one or more pages have no native text; OCR enrichment required'}
    ir={'schema_version':SCHEMA_VERSION,'model_version':MODEL_VERSION,'document_id':'pdf-'+digest[:20],
        'revision':'original-'+FRONTEND_VERSION.rsplit('/',1)[1],
        'source_artifacts':[{'id':'pdf','kind':'pdf','path':str(pdf),'sha256':digest,'page_count':len(pages)}],
        'root_id':'paper','nodes':nodes,'layout':{'pages':pages},
        'coverage':{'pages':dict(complete if readable else partial),
                    'bibliography':{'status':'partial','reason':'main bibliography candidate selected; full field/boundary coverage requires verification'},
                    'reference_uses':{'status':'partial','reason':'numeric and author-year source pass; semantic/OCR coverage verification pending'}},
        'profile':{'id':'archive479-citations-v1'},'metadata':{'frontend_version':FRONTEND_VERSION,'bibliography_heading':bibliography_heading,'bibliography_selection':bibliography_method},'extensions':{}}
    if bibliography_observations:
        ir['metadata']['bibliography_observations']=bibliography_observations
        ir['coverage']['bibliography']={'status':'partial','reason':'main bibliography unlocated after optional model error; no candidate selected'}
        ir['coverage']['reference_uses']={'status':'partial','reason':'bibliography unlocated; citation binding and semantic coverage remain unverified'}
    attach_citations(ir)
    validate_ir(ir,pdf.parent)
    return ir
