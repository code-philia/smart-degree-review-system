"""Source-grounded expansion of an explicitly grouped abstract contribution."""
from copy import deepcopy
import re


def _key(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _descendant(sections, child, parent):
    seen=set()
    while child in sections and child not in seen:
        if child==parent:return True
        seen.add(child);child=sections[child].get('parent_id')
    return False


def _anchors(text):
    # Long exact source fragments, not semantic or numerical similarity.
    return {part[i:i+size] for part in re.findall(r'[\u3400-\u9fff]{4,}|[A-Za-z][A-Za-z0-9-]{3,}',text)
            for size in range(4,min(10,len(part))+1) for i in range(len(part)-size+1)}


def expand_scope(structure, context, model, support):
    result=deepcopy(structure)
    sections=model['sections']
    abstract=_key(context.get('abstract',''))
    contributions={c['id']:c for c in result.get('contributions',[]) if isinstance(c,dict) and c.get('id') and _key(c.get('text')) and _key(c['text']) in abstract}
    declarations={d['id']:d for d in result.get('declarations',[])}
    roots={sid:s for sid,s in sections.items() if s.get('parent_id') is None}
    for mapping in result.get('mappings',[]):
        # Never trust a locator-supplied expansion or keep stale scope evidence.
        mapping.pop('contribution_scope',None)
        d=declarations.get(mapping.get('declaration_id'),{})
        if d.get('contribution_id') not in contributions:continue
        method=str(d.get('method') or '').strip()
        scope_text=str(d.get('text') or '')
        named_method = bool(re.search(r'[A-Za-z][A-Za-z0-9-]{3,}',method))
        if named_method and _key(method) in _key(d.get('source_context') or d.get('text') or ''):continue
        if not re.search(r'相关方法|各(?:种|类)?方法|多种方法|两种方法|多个方法|所有方法|总体|整体|\bacross\b|related methods',scope_text,re.I):continue
        phrases=re.findall(r'(?:面向|针对|关于)([\u3400-\u9fff]{4,24}?)(?:的(?:相关)?方法|相关方法|问题)',_key(scope_text))
        for phrase in dict.fromkeys(phrases):
            related=[c for c in contributions.values() if phrase in _key(c['text'])]
            if d['contribution_id'] not in {c['id'] for c in related}:continue
            from_native_spans = not 2 <= len(related) <= 4
            if from_native_spans:
                # A locator may group several child methods into one summary
                # contribution. Derive children only from exact first-person
                # native abstract descriptions, never background or numbers.
                related = [{'id': 'native-span:' + span['id'], 'text': span['text'],
                            'abstract_span_id': span['id']}
                           for span in context.get('abstract_spans') or []
                           if isinstance(span.get('text'), str) and _key(span['text']) in abstract
                           and phrase in _key(span['text'])
                           and (re.search(r'本文|本研究', _key(span['text']))
                                or re.search(r'\b(?:we|our)\b', span['text'], re.I))
                           and not re.search(r'(?:不|未|没有|并未).{0,3}(?:研究|提出|设计|构建)|\b(?:not|never)\s+(?:study|propos|develop)',
                                             _key(span['text']) if re.search(r'[\u3400-\u9fff]', span['text']) else span['text'], re.I)
                           and re.search(r'研究|提出|设计|构建|propos|develop', _key(span['text']), re.I)]
            matched={}
            for c in related:
                distinctive=_anchors(_key(c['text']).replace(phrase,''))
                hits=[]
                for sid,section in roots.items():
                    title=_key(section.get('title',''))
                    rest=title.replace(phrase,'')
                    if phrase in title and distinctive & _anchors(rest):hits.append(sid)
                if len(hits)==1:matched[c['id']]=hits[0]
            if from_native_spans:
                related = [c for c in related if c['id'] in matched]
            if not 2 <= len(related) <= 4 or len(matched)!=len(related) or len(set(matched.values()))<2:continue
            if mapping.get('chapter_id') not in matched.values():continue
            chapter_ids=list(dict.fromkeys(matched.values()))
            experiment_ids=[sid for sid,s in sections.items() if s.get('parent_id') is not None and any(_descendant(sections,sid,ch) for ch in chapter_ids) and support(model,sid)]
            if not experiment_ids or len(experiment_ids)>48:continue
            if named_method:
                d['model_method'] = d['method']
                d['method'] = ''
            mapping['contribution_scope']={'version':'source-grounded-child-methods/1.0','scope_phrase':phrase,
                'chapter_ids':chapter_ids,'experiment_section_ids':experiment_ids,
                'contribution_ids':[c['id'] for c in related],
                'abstract_evidence':[{'contribution_id':c['id'],'quote':c['text'],'abstract_span_id':c.get('abstract_span_id')} for c in related],
                'chapter_evidence':[{'chapter_id':sid,'quote':roots[sid]['title']} for sid in chapter_ids]}
            break
    return result
