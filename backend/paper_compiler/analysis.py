"""Shared source-grounded passes, external identity, and citation-purpose analysis."""
import hashlib
import json
import re
from pathlib import Path
from .contracts import ir_hash,validate_analysis
from .storage import json_bytes,write_json_atomic
from .registry import REGISTRY,FIELD_TYPES
from .identity import resolve_identity
from .citations import citation_context

VERSION='shared-analysis/1.1'
def unknown(reason):return {'state':'unknown','reason':reason}
def observed(value,ids):return {'state':'observed','value':value,'evidence_ids':list(dict.fromkeys(ids))}
def _norm(text):return re.sub(r'\s+',' ',str(text)).strip()

def locate_quote(text,quote):
    if not isinstance(quote,str) or not quote.strip():raise ValueError('empty source quote')
    offset=text.find(quote)
    if offset>=0:return offset,offset+len(quote)
    chars=[];offsets=[]
    for i,ch in enumerate(text):
        if ch.isspace():
            if not chars or chars[-1]==' ':continue
            chars.append(' ');offsets.append(i)
        else:chars.append(ch);offsets.append(i)
    normalized=''.join(chars);needle=_norm(quote);start=normalized.find(needle)
    if start<0:raise ValueError('quote does not occur in supplied source')
    return offsets[start],offsets[start+len(needle)-1]+1

def base_analysis(ir):
    return {'schema_version':'paper-analysis/1.0','paper_ir_sha256':ir_hash(ir),'model_version':ir['model_version'],
        'capability_versions':{name:cap['version'] for name,cap in REGISTRY['capabilities'].items()},
        'results':{},'coverage':{},'entities':[],'evidence':[],'bindings':[],'edges':[],'producer':VERSION}

def _add_evidence(a,item):
    if not any(old['id']==item['id'] for old in a['evidence']):a['evidence'].append(item)
    return item['id']

def _extract_field(node,name,item,complete,a):
    if not isinstance(item,dict):return unknown('field not returned by extraction')
    if item.get('state')=='confirmed_absent' and complete:
        return {'state':'confirmed_absent','search_scope':node['id'],'evidence_ids':[node['id']]}
    if item.get('state')!='observed':return unknown(item.get('reason','field extraction uncertain'))
    value=item.get('value');typ=FIELD_TYPES[name]
    if (typ=='array' and (not isinstance(value,list) or not all(isinstance(v,str) for v in value))) or (typ=='string' and not isinstance(value,str)):
        return unknown('field type did not match extraction contract')
    try:
        start,end=locate_quote(node['text'],item.get('quote'))
        quote=node['text'][start:end]
        # Transcription may join whitespace but may not replace or invent content.
        if any(_norm(v) not in _norm(quote) for v in (value if isinstance(value,list) else [value])):raise ValueError('value not supported by quote')
    except ValueError:return unknown('untraceable field extraction')
    eid='span-'+hashlib.sha256(json_bytes([node['id'],name,start,end,quote])).hexdigest()[:24]
    _add_evidence(a,{'id':eid,'kind':'source_span','node_id':node['id'],'start':start,'end':end,'quote':quote})
    return {**observed(value,[eid]),'source_range':[start,end]}

def parse_entries(ir,a,client,*,batch_size=2):
    entries=[n for n in ir['nodes'] if n['kind']=='BibliographyEntry']
    results=a['results'].setdefault('bibliography_fields',{})
    instructions="""Extract bibliographic fields from exactly the supplied entry text. Do not judge any rule.
Return {entries:[{id,complete:boolean,fields:{FIELD:{state:'observed',value:STRING_OR_ARRAY,quote:EXACT_SOURCE_SUBSTRING}},absent:[FIELD_NAMES_CONFIRMED_NOT_PRESENT]}]}.
Use the supplied field names/types. Include observed fields only in fields; list explicitly confirmed absent names in absent. Omitted names stay unknown. complete means this is one readable complete entry, not that all fields are present.
Never invent or correct metadata. Preserve punctuation and spelling; whitespace across wrapped lines may be collapsed. Each observed value must occur inside its quote. Authors are an array of transcribed author names.
type_code and carrier_code exclude brackets; date/access_date exclude brackets; year is a string. title excludes authors and resource marker. institution is the degree granting institution for a thesis. conference is the meeting name. DOI/URL are optional source fields; omit them only as confirmed_absent after examining the entire entry.
If the entry contains several concatenated works or incomplete boundary, set complete=false; absences then remain unknown.
"""
    for start in range(0,len(entries),batch_size):
        batch=entries[start:start+batch_size]
        if client is None:
            answer={}
        else:answer=client.complete_json('bibliography-fields/1.1',instructions,{'field_types':FIELD_TYPES,'entries':[{'id':n['id'],'text':n['text']} for n in batch]},6000)
        raw={item.get('id'):item for item in answer.get('entries',[]) if isinstance(item,dict)}
        for node in batch:
            item=raw.get(node['id'],{});complete=item.get('complete') is True;fields=item.get('fields',{})
            fields=dict(fields) if isinstance(fields,dict) else {}
            for name in item.get('absent',[]):
                if name in FIELD_TYPES and name not in fields:fields[name]={'state':'confirmed_absent'}
            facts={name:_extract_field(node,name,fields.get(name),complete,a) for name in FIELD_TYPES}
            results[node['id']]=facts
            a['coverage'][node['id']]={'status':'complete' if complete else 'partial','protocol':'bibliography-fields/1.1'}
    _entry_shapes(ir,a)
    return a

def _value(fields,name,default=None):
    field=fields.get(name,{})
    return field.get('value',default) if field.get('state')=='observed' else default

def _entry_shapes(ir,a):
    results=a['results'].setdefault('bibliography_shape',{})
    for n in ir['nodes']:
        if n['kind']!='BibliographyEntry':continue
        fields=a['results'].get('bibliography_fields',{}).get(n['id'],{});text=n['text'];key=n['attrs'].get('key','')
        carrier=_value(fields,'carrier_code');url=_value(fields,'url')
        electronic=observed(True,[n['id']]) if carrier or url else observed(False,[n['id']]) if fields.get('carrier_code',{}).get('state')=='confirmed_absent' and fields.get('url',{}).get('state')=='confirmed_absent' else unknown('medium unresolved')
        marker=re.search(r'[\[［]\s*[A-Za-z]{1,3}\s*(?:/\s*[A-Za-z]{1,2}\s*)?[\]］]',text)
        seq=[name for _,name in sorted((item['source_range'][0],name) for name,item in fields.items() if 'source_range' in item)]
        results[n['id']]={'electronic':electronic,'type_bracketed':observed(bool(marker),[n['id']]),
            'label_bracketed':observed(bool(re.match(r'^\s*[\[［]\d+[\]］]',text)),[n['id']]),
            'system':observed('numeric' if str(key).isdigit() else 'author_year',[n['id']]),'field_sequence':observed(seq,[n['id']])}

def bind_references(ir,a):
    entries=[n for n in ir['nodes'] if n['kind']=='BibliographyEntry'];bindings=[]
    for use in ir['nodes']:
        if use['kind']!='ReferenceUse' or use['attrs'].get('namespace')!='bibliography':continue
        selector=use['attrs'].get('selector',{});value=str(selector.get('value',''))
        if selector.get('kind')=='numeric':targets=[n['id'] for n in entries if n['attrs'].get('key')==value]
        else:
            # Author-year bindings require both components and a unique entry.
            targets=[];year=re.search(r'(?:18|19|20)\d{2}[a-z]?',value)
            if year:
                author=re.sub(r'[()（）,，;；|]',' ',value[:year.start()]).strip()
                for n in entries:
                    fields=a['results'].get('bibliography_fields',{}).get(n['id'],{})
                    if year.group() in n['text'] and author and any(author.casefold() in name.casefold() or name.casefold() in author.casefold() for name in _value(fields,'authors',[])):targets.append(n['id'])
        binding={'use_id':use['id'],'status':'resolved' if len(targets)==1 else 'ambiguous' if targets else 'unresolved','target_ids':targets}
        bindings.append(binding)
    a['bindings']=bindings
    return bindings

def citation_syntax(ir,a):
    results=a['results'].setdefault('citation_syntax',{})
    for n in ir['nodes']:
        if n['kind']!='CitationGroup':continue
        text=n['text'].strip();numeric=bool(re.fullmatch(r'[\[［][\d\s,，;；\-–—−]+[\]］]',text))
        results[n['id']]={k:observed(v,[n['id']]) for k,v in {'system':'numeric' if numeric else 'author_year','opening':text[:1],'closing':text[-1:],
            'separators':re.findall(r'[,，;；]',text),'range_separators':re.findall(r'[\-–—−]',text),'numbers':re.findall(r'\d+',text) if numeric else []}.items()}
        results[n['id']]['automatic_footnote']=unknown('automatic numbering cannot be established from PDF text')

def judge_relevance(context,content,client):
    available=[c for c in content if c.get('status')=='ok' and c.get('text')]
    if not available or client is None:return unknown('citation content or semantic analyzer unavailable')
    instructions="""Compare THIS citation purpose to the identified work. A use can provide a method, definition, data, background, comparison or criticism; disagreement and different application disciplines can be relevant. Do not compare only global paper topics.
Return relation ('related','unrelated','unknown'), purpose, intent_quote (exact from supplied citing context), evidence_id, evidence_quote (exact from that content), basis ('explicit_support','explicit_scope_contradiction','missing_detail','insufficient'), reason.
Only use unrelated with positive explicit evidence that the cited work cannot serve this purpose. Missing abstract details, empty search, inaccessible full text or a broad topic difference is insufficient. If an abstract is insufficient for a detailed claim, return unknown so retrieval can enrich. Consider each source's contribution in a grouped citation. Do not invent quotes.
"""
    data={'context':context,'content':[{k:v for k,v in c.items() if k in {'id','text','level','coverage'}} for c in available]}
    result=client.complete_json('citation-purpose/1.0',instructions,data,1800)
    item=next((c for c in available if c['id']==result.get('evidence_id')),None)
    relation=result.get('relation');basis=result.get('basis')
    if item is None or relation not in {'related','unrelated'}:return unknown(result.get('reason','semantic evidence insufficient'))
    citing='\n'.join(str(v) for k,v in context.items() if k in {'paragraph','text','previous_text','next_text'} and v)
    try:
        intent_span=locate_quote(citing,result.get('intent_quote'))
        evidence_span=locate_quote(item['text'],result.get('evidence_quote'))
    except ValueError:return unknown('semantic judgment quotes do not match sources')
    if relation=='unrelated' and basis!='explicit_scope_contradiction':return unknown('absence of detail does not prove irrelevance')
    if relation=='related' and basis!='explicit_support':return unknown('relevance lacks positive supporting evidence')
    return {**observed(relation=='related',[item['id']]),'purpose':result.get('purpose'),'intent_quote':result['intent_quote'],
        'evidence_quote':result['evidence_quote'],'content_range':list(evidence_span),'reason':result.get('reason',''),'basis':basis}

def enrich(ir,rule_packages,*,client,gateway,cache_dir:Path):
    required={name for package in rule_packages for name in package['rule_ir']['requires']}
    fingerprint=hashlib.sha256(json_bytes({'ir':ir_hash(ir),'version':VERSION,'capabilities':REGISTRY,'required':sorted(required)})).hexdigest()
    path=Path(cache_dir)/(fingerprint+'.json')
    if path.exists():
        cached=json.loads(path.read_text());validate_analysis(ir,cached);return cached
    a=base_analysis(ir);parse_entries(ir,a,client);bind_references(ir,a);citation_syntax(ir,a);ordering_facts(ir,a)
    if required & {'external_work','citation_relevance'}:
        external=a['results'].setdefault('external_work',{})
        for node in ir['nodes']:
            if node['kind']!='BibliographyEntry':continue
            fields=a['results']['bibliography_fields'][node['id']]
            query={name:_value(fields,name) for name in ['title','authors','year','doi']}
            query['authors']=query.get('authors') or []
            records=gateway.lookup(query) if gateway and query.get('title') else []
            for record in records:_add_evidence(a,record)
            identity=resolve_identity(query,records,client=client)
            external[node['id']]={'exists':{k:v for k,v in identity.items() if k not in {'work','metadata_conflicts','method'}}}
            if identity.get('value') is True:
                work=identity['work'];eid='work-'+hashlib.sha256(json_bytes(work)).hexdigest()[:24]
                if not any(e['id']==eid for e in a['entities']):a['entities'].append({'id':eid,'kind':'ExternalWork',**work})
                a['edges'].append({'type':'identifies','from':node['id'],'to':eid,'evidence_ids':identity['evidence_ids']})
                external[node['id']]['available_fields']=observed([name for name in FIELD_TYPES if work.get(name)],identity['evidence_ids'])
            else:external[node['id']]['available_fields']=unknown('work identity unresolved')
    if 'citation_relevance' in required:
        relevant=a['results'].setdefault('citation_relevance',{});nodes={n['id']:n for n in ir['nodes']};entities={e['id']:e for e in a['entities']}
        work_edges={e['from']:e['to'] for e in a['edges'] if e['type']=='identifies'}
        for binding in a['bindings']:
            use_id=binding['use_id']
            if binding['status']!='resolved' or binding['target_ids'][0] not in work_edges:
                relevant[use_id]={'related':unknown('citation binding or external work identity unresolved')};continue
            work=entities[work_edges[binding['target_ids'][0]]];context=citation_context(ir,use_id)
            content=gateway.content(work)
            for item in content:_add_evidence(a,item)
            result=judge_relevance(context,content,client)
            # One bounded metadata enrichment when content remains insufficient. No search-result absence becomes a negative.
            if result['state']=='unknown':
                extra=gateway.lookup({'title':work.get('title'),'doi':work.get('doi'),'authors':work.get('authors',[]),'year':work.get('year')})
                for item in extra:_add_evidence(a,item)
                match=resolve_identity(work,extra)
                if match.get('value') is True:
                    extra_content=gateway.content(match['work']);known={c['id'] for c in content}
                    fresh=[c for c in extra_content if c['id'] not in known and c.get('status')=='ok']
                    if fresh:
                        for item in fresh:_add_evidence(a,item)
                        result=judge_relevance(context,content+fresh,client)
            relevant[use_id]={'related':result}
            if result.get('state')=='observed':
                iid='intent-'+use_id;a['entities'].append({'id':iid,'kind':'CitationIntent','use_id':use_id,'purpose':result.get('purpose'),'quote':result.get('intent_quote')})
                a['edges'].append({'type':'relevant_to' if result['value'] else 'contradicts','from':work['id'],'to':iid,'evidence_ids':result['evidence_ids']})
    validate_analysis(ir,a);write_json_atomic(path,a);return a


def ordering_facts(ir,a):
    bibliography=a['results'].setdefault('bibliography_order',{});citations=a['results'].setdefault('citation_order',{})
    for index,node in enumerate(n for n in ir['nodes'] if n['kind']=='BibliographyEntry'):
        key=str(node['attrs'].get('key',''))
        bibliography[node['id']]={'position':observed(index+1,[node['id']]),'numeric_value':observed(int(key),[node['id']]) if key.isdigit() else unknown('not a numeric bibliography key')}
    seen={};complete=ir['coverage'].get('reference_uses',{}).get('status')=='complete'
    for node in ir['nodes']:
        if node['kind']!='ReferenceUse':continue
        selector=node['attrs'].get('selector',{});value=str(selector.get('value',''));first=value not in seen
        if first:seen[value]=len(seen)+1
        citations[node['id']]={'numeric_value':observed(int(value),[node['id']]) if selector.get('kind')=='numeric' and value.isdigit() else unknown('not a numeric citation'),
            'first_appearance_rank':observed(seen[value],[node['id']]) if complete else unknown('incomplete citation extraction prevents ordinal judgment'),
            'is_first_use':observed(first,[node['id']]) if complete else unknown('earlier unobserved citations are possible')}
