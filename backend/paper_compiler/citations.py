"""Citation syntax and source anchors; this module makes no compliance judgment."""
import re

NUMERIC = re.compile(r'[\[［](\d{1,4}(?:\s*[-–—,，;；]\s*\d{1,4})*)[\]］)）]')
PAREN_YEAR = re.compile(r'[（(]([A-Za-z\u4e00-\u9fff][^()（）\n]{0,60}?)[,，、 ]+((?:18|19|20)\d{2}[a-z]?)[）)]')
NARRATIVE_YEAR = re.compile(r'([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?|[\u4e00-\u9fff]{2,4}(?:等)?)\s*[（(]((?:18|19|20)\d{2}[a-z]?)[）)]')


def source_spans(ir, node, start=0, end=None):
    text = node.get('text') or ''
    end = len(text) if end is None else end
    lookup = {line['id']: line for page in ir['layout']['pages'] for line in page['lines']}
    result = []
    for span in node['provenance']:
        if span['kind'] != 'source' or 'line_id' not in span:
            result.append(dict(span))
            continue
        left, right = span['node_text_start'], span['node_text_end']
        lo, hi = max(start, left), min(end, right)
        if lo >= hi:
            continue
        line = lookup[span['line_id']]
        chars = [c for c in line['chars'] if c['end'] > lo-left and c['start'] < hi-left]
        box = [min(c['bbox'][0] for c in chars), min(c['bbox'][1] for c in chars),
               max(c['bbox'][2] for c in chars), max(c['bbox'][3] for c in chars)] if chars else list(span['bbox'])
        result.append({**span, 'bbox': box, 'text_offsets': [lo-left,hi-left],
                       'node_text_start': lo-start, 'node_text_end': hi-start})
    return result


def attach_citations(ir):
    bibliography = next((n for n in ir['nodes'] if n['kind']=='Bibliography'), None)
    scope = bibliography['id'] if bibliography else ir['root_id']
    for node in list(ir['nodes']):
        if node['kind'] not in {'Paragraph','Caption'} or node['attrs'].get('role') in {'running_header','running_footer'}:
            continue
        text = node['text'] or ''
        matches = []
        for match in NUMERIC.finditer(text):
            before = text[max(0,match.start()-40):match.start()]
            if re.search(r'[=＝]\s*$',before) or re.search(r'(?:array|vector|matrix|数组|区间)\s*$',before,re.I):
                continue
            selectors = []
            for part in re.split(r'[,，;；]',match.group(1)):
                values = re.split(r'[-–—]',part.strip())
                if len(values)==2 and 0 < int(values[0]) <= int(values[1]) <= int(values[0])+100:
                    selectors.extend({'kind':'numeric','value':str(i)} for i in range(int(values[0]),int(values[1])+1))
                else:
                    selectors.append({'kind':'numeric' if len(values)==1 else 'unparsed','value':part.strip()})
            matches.append((match.start(),match.end(),selectors,'numeric'))
        for pattern in (PAREN_YEAR,NARRATIVE_YEAR):
            for match in pattern.finditer(text):
                if any(match.start()<end and match.end()>start for start,end,_,_ in matches):
                    continue
                matches.append((match.start(),match.end(),[{'kind':'author_year','value':match.group(1).strip()+'|'+match.group(2)}],'author_year'))
        for ordinal,(start,end,selectors,style) in enumerate(sorted(matches)):
            group_id = node['id']+'-citation-'+str(ordinal)
            spans = source_spans(ir,node,start,end)
            group = {'id':group_id,'kind':'CitationGroup','text':text[start:end],
                     'children':[],'attrs':{'style':style,'marker':text[start:end]},'provenance':spans}
            node['children'].append(group_id)
            ir['nodes'].append(group)
            for number,selector in enumerate(selectors):
                use_id=group_id+'-use-'+str(number)
                group['children'].append(use_id)
                ir['nodes'].append({'id':use_id,'kind':'ReferenceUse','text':text[start:end],'children':[],
                    'attrs':{'namespace':'bibliography','expected_kind':'BibliographyEntry','scope_id':scope,'selector':selector},
                    'provenance':[dict(span) for span in spans]})
    return ir


def citation_context(ir: dict, use_id: str) -> dict:
    nodes={node['id']:node for node in ir['nodes']}
    parents={child:node['id'] for node in ir['nodes'] for child in node['children']}
    if use_id not in nodes or nodes[use_id]['kind']!='ReferenceUse':
        raise ValueError('citation use is missing')
    ancestors=[];current=use_id
    while current in parents:
        current=parents[current];ancestors.append(nodes[current])
    paragraph=next((node for node in ancestors if node['kind'] in {'Paragraph','Caption'}),None)
    section=next((node for node in ancestors if node['kind']=='Section'),None)
    heading=next((nodes[child]['text'] for child in section['children'] if nodes[child]['kind']=='Heading'),None) if section else None
    context={'use_id':use_id,'node_id':paragraph['id'] if paragraph else use_id,
             'text':paragraph['text'] if paragraph else nodes[use_id]['text'], 'section_heading':heading,
             'previous_text':None,'next_text':None,'selector':nodes[use_id]['attrs']['selector']}
    if paragraph and paragraph['id'] in parents:
        siblings=nodes[parents[paragraph['id']]]['children'];index=siblings.index(paragraph['id'])
        if index:context['previous_text']=nodes[siblings[index-1]]['text']
        if index+1<len(siblings):context['next_text']=nodes[siblings[index+1]]['text']
    return context
