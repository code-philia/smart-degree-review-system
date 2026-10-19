"""Shared source-grounded passes, external identity, and citation-purpose analysis."""
import hashlib
import json
import os
import re
from pathlib import Path
from .contracts import ir_hash,validate_analysis
from .storage import json_bytes,write_json_atomic
from .registry import REGISTRY,FIELD_TYPES
from .identity import resolve_identity, IDENTITY_POLICY
from .citations import citation_context

VERSION='shared-analysis/1.5'
BIBLIOGRAPHY_EXTRACTION_POLICY='source-linewrap-preserve-hyphen/1.0'
BIBLIOGRAPHY_INSTRUCTIONS="""Extract bibliographic fields from exactly the supplied entry text. Do not judge any rule.
Return {entries:[{id,complete:boolean,fields:{FIELD:{state:'observed',value:STRING_OR_ARRAY,quote:EXACT_SOURCE_SUBSTRING}},absent:[FIELD_NAMES_CONFIRMED_NOT_PRESENT]}]}.
Use the supplied field names/types. Include observed fields only in fields; list explicitly confirmed absent names in absent. Omitted names stay unknown. complete means this is one readable complete entry, not that all fields are present.
Never invent or correct metadata. Preserve punctuation and spelling; whitespace across wrapped lines may be collapsed. Each observed value must occur inside its quote. Authors are an array of transcribed author names.
type_code and carrier_code exclude brackets; date/access_date exclude brackets; year is a string. title excludes authors and resource marker. institution is the degree granting institution for a thesis. conference is the meeting name. DOI/URL are optional source fields; omit them only as confirmed_absent after examining the entire entry.
If the entry contains several concatenated works or incomplete boundary, set complete=false; absences then remain unknown.
"""

BIBLIOGRAPHY_BATCH_INSTRUCTIONS = """
This batch contains independent bibliography entries from one paper.
Keep the original entries response schema and use only the supplied entry IDs.
Transcribe each field solely from that entry's own text; never borrow another
entry's quote, authors, metadata or completeness. Return every supplied entry.
An omitted or uncertain field remains unknown. Complete describes only that
entry's readable boundary; absence does not establish any external-world fact.
Do not judge document compliance or whether the referenced work exists.
"""


def bibliography_execution_policy():
    """Public extraction settings; mode1 retains the historical two-entry request."""
    raw = os.environ.get('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '1').strip()
    if raw not in {str(n) for n in range(1, 9)}:
        raise ValueError('PAPER_COMPILER_ANALYSIS_BATCH_SIZE must be an integer from 1 to 8')
    opt_in = raw != '1'
    size = int(raw) if opt_in else 2
    instructions = BIBLIOGRAPHY_INSTRUCTIONS + (BIBLIOGRAPHY_BATCH_INSTRUCTIONS if opt_in else '')
    return {'schema_version':'bibliography-execution/1.0', 'opt_in':opt_in,
            'protocol':'bibliography-entry-batch/1.0' if opt_in else 'bibliography-fields/1.1',
            'task':'bibliography-fields/1.1', 'batch_size':size,
            'input_soft_limit_bytes':128*1024 if opt_in else None,
            'max_tokens_per_entry':3000, 'minimum_batch_max_tokens':6000,
            'max_tokens_per_batch':min(16384, max(6000, 3000*size)),
            'prompt_sha256':hashlib.sha256(instructions.encode()).hexdigest(),
            'extraction_policy':BIBLIOGRAPHY_EXTRACTION_POLICY}


def _bibliography_data(batch):
    return {'field_types':FIELD_TYPES,'entries':[{'id':n['id'],'text':n['text']} for n in batch]}


def _bibliography_batches(entries, size, soft_limit):
    if soft_limit is None:
        for start in range(0, len(entries), size):
            yield entries[start:start+size]
        return
    batch = []
    for node in entries:
        candidate = batch + [node]
        if batch and (len(candidate) > size or len(json.dumps(_bibliography_data(candidate), ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')) > soft_limit):
            yield batch
            batch = []
        batch.append(node)
    if batch:
        yield batch

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

def _linewrap_transcription(quote):
    # Join only a single physical line break after an alphanumeric hyphen.
    # Keep the hyphen and record exactly which source whitespace was removed.
    pattern=r'(?<=[^\W_])-(?P<gap>[ \t]*(?:\r\n|\n|\r)[ \t]*)(?=[^\W_])'
    spans=[match.span('gap') for match in re.finditer(pattern,quote)]
    pieces=[];offset=0
    for start,end in spans:
        pieces.append(quote[offset:start]);offset=end
    pieces.append(quote[offset:])
    return ''.join(pieces),spans

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
        # Plain whitespace transcription remains supported. Any additional
        # line-wrap joining requires an exact source quote and a reversible map.
        values=value if isinstance(value,list) else [value]
        joins=[]
        if any(_norm(v) not in _norm(quote) for v in values):
            joined,joins=_linewrap_transcription(quote)
            if item.get('quote')!=quote or not joins or any(_norm(v) not in _norm(joined) for v in values):
                raise ValueError('value not supported by quote')
    except ValueError:return unknown('untraceable field extraction')
    eid='span-'+hashlib.sha256(json_bytes([node['id'],name,start,end,quote])).hexdigest()[:24]
    evidence={'id':eid,'kind':'source_span','node_id':node['id'],'start':start,'end':end,'quote':quote}
    if joins:
        evidence.update(transcription_policy=BIBLIOGRAPHY_EXTRACTION_POLICY,
                        linewrap_join_ranges=[[start+a,start+b] for a,b in joins])
    _add_evidence(a,evidence)
    return {**observed(value,[eid]),'source_range':[start,end]}

def parse_entries(ir,a,client,*,batch_size=None):
    entries=[n for n in ir['nodes'] if n['kind']=='BibliographyEntry']
    results=a['results'].setdefault('bibliography_fields',{})
    execution = bibliography_execution_policy() if batch_size is None else None
    opt_in = bool(execution and execution['opt_in'])
    if batch_size is None:batch_size = execution['batch_size']
    instructions = BIBLIOGRAPHY_INSTRUCTIONS + (BIBLIOGRAPHY_BATCH_INSTRUCTIONS if opt_in else '')
    for batch in _bibliography_batches(entries, batch_size, execution['input_soft_limit_bytes'] if opt_in else None):
        max_tokens = min(16384, max(6000, 3000*len(batch))) if opt_in else 6000
        if client is None:
            answer={}
        else:answer=client.complete_json('bibliography-fields/1.1',instructions,_bibliography_data(batch),max_tokens)
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
    _resource_attributes(ir,a)
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
            'system':unknown('entry label unresolved') if isinstance(key,dict) else observed('numeric' if str(key).isdigit() else 'author_year',[n['id']]),'field_sequence':observed(seq,[n['id']])}

def _resource_attributes(ir,a):
    resolved=a.setdefault('node_attributes',{})
    names={'M':'book','J':'journal_article','N':'newspaper_article','C':'conference','D':'thesis','R':'report',
        'S':'standard','P':'patent','EB':'webpage','A':'archive','CM':'map','DS':'dataset','PP':'preprint',
        'G':'collection','CP':'computer_program','DB':'database','Z':'other'}
    for node in ir['nodes']:
        if node['kind']!='BibliographyEntry':continue
        original=node['attrs'].get('resource_type')
        if original is not None and not (isinstance(original,dict) and original.get('state') in {'unknown','not_applicable'}):continue
        fields=a['results'].get('bibliography_fields',{}).get(node['id'],{});item=fields.get('type_code',{})
        code=_value(fields,'type_code');kind=names.get(str(code).upper()) if code else None
        if kind=='book' and re.search(r'[\]］]\s*//',node['text']):kind='book_chapter'
        observation=observed(kind,item.get('evidence_ids',[])+[node['id']]) if kind else unknown('resource type not established from the source marker')
        resolved[node['id']]={'resource_type':observation}


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
        results[n['id']]={k:observed(v,[n['id']]) for k,v in {'system':'numeric' if numeric else 'author_year','form':'bracketed' if numeric else 'parenthetical' if text[:1] in '(（' else 'narrative','opening':text[:1],'closing':text[-1:],
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

def capability_plan(packages):
    plan={}
    for package in packages:
        for name in package['rule_ir']['requires']:
            cap=package['registry']['capabilities'][name]
            if name in plan and plan[name]!=cap:raise ValueError('conflicting capability versions: '+name)
            plan[name]=cap
    for name,cap in plan.items():
        if name in REGISTRY['capabilities']:
            if cap['version']!=REGISTRY['capabilities'][name]['version']:raise ValueError('unsupported builtin capability version: '+name)
        elif cap.get('implementation')!='isolated_pure_python':raise ValueError('unsupported capability implementation: '+name)
        elif hashlib.sha256(Path(cap['code_path']).read_bytes()).hexdigest()!=cap['code_sha256']:raise ValueError('capability code hash mismatch')
    return plan

def generated_passes(ir,a,plan):
    from .capabilities import run_capability
    for name,cap in plan.items():
        if name in REGISTRY['capabilities']:continue
        output=a['results'].setdefault(name,{})
        for node in ir['nodes']:
            if node['kind'] not in cap['targets']:continue
            if node.get('text') is None:
                output[node['id']]={field:unknown('source text unavailable for generated analysis') for field in cap['fields']};continue
            values=run_capability(cap,{'node':node,'facts':{}})
            output[node['id']]={field:observed(value,[node['id']]) for field,value in values.items()}
    return a

def enrich(ir,rule_packages,*,client,gateway,cache_dir:Path,snapshot_id=None):
    plan=capability_plan(rule_packages);required=set(plan)
    from datetime import datetime,timezone
    from .evidence import VERSION as EVIDENCE_VERSION,CONTENT_VERSION
    snapshot_id=snapshot_id or datetime.now(timezone.utc).date().isoformat()
    config=getattr(client,'config',{})
    policy={'model':{k:config.get(k) for k in ['MAAS_MODEL','MAAS_MODEL_VERSION']},'offline':client is None,'providers':getattr(gateway,'providers',[]),'evidence_version':EVIDENCE_VERSION,'content_version':CONTENT_VERSION,'snapshot':snapshot_id,'frozen_evidence':getattr(gateway,'snapshot_id',None)}
    bibliography_policy = bibliography_execution_policy()
    bibliography_required=bool(required & {'bibliography_fields','bibliography_shape','external_work','citation_relevance'})
    if bibliography_policy['opt_in']:
        policy['bibliography']={k:v for k,v in bibliography_policy.items()
                                if k!='extraction_policy' or bibliography_required}
    if bibliography_required:policy['bibliography_extraction']=BIBLIOGRAPHY_EXTRACTION_POLICY
    if required & {'external_work','citation_relevance'}:
        policy['identity_resolution'] = IDENTITY_POLICY
    fingerprint=hashlib.sha256(json_bytes({'ir':ir_hash(ir),'version':VERSION,'capabilities':plan,'required':sorted(required),'policy':policy})).hexdigest()
    path=Path(cache_dir)/(fingerprint+'.json')
    if path.exists():
        cached=json.loads(path.read_text());validate_analysis(ir,cached);return cached
    a=base_analysis(ir);a['policy']=policy
    a['capability_versions'].update({name:cap['version'] for name,cap in plan.items()})
    if required & {'bibliography_fields','bibliography_shape','external_work','citation_relevance'}:parse_entries(ir,a,client)
    bind_references(ir,a);citation_syntax(ir,a);ordering_facts(ir,a)
    if required & {'external_work','citation_relevance'}:
        external=a['results'].setdefault('external_work',{})
        for node in ir['nodes']:
            if node['kind']!='BibliographyEntry':continue
            fields=a['results']['bibliography_fields'][node['id']]
            query={name:_value(fields,name) for name in ['title','authors','year','doi']}
            query['authors']=query.get('authors') or []
            records=gateway.lookup(query) if gateway and query.get('title') else []
            for record in records:_add_evidence(a,record)
            identity_entry = dict(query)
            source_url = _value(fields, 'url')
            if isinstance(source_url, str) and source_url.strip():
                identity_entry['url'] = source_url
            identity=resolve_identity(identity_entry,records,client=client)
            external[node['id']]={'exists':{k:v for k,v in identity.items() if k not in {'work','metadata_conflicts','method'}}}
            if identity.get('value') is True:
                work=identity['work'];eid='work-'+hashlib.sha256(json_bytes(work)).hexdigest()[:24]
                if not any(e['id']==eid for e in a['entities']):a['entities'].append({'id':eid,'kind':'ExternalWork',**work})
                a['edges'].append({'type':'identifies','from':node['id'],'to':eid,'evidence_ids':identity['evidence_ids']})
                external[node['id']]['available_fields']={**observed([name for name in FIELD_TYPES if work.get(name)],identity['evidence_ids']),'complete':False}
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
    generated_passes(ir,a,plan)
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
        citations[node['id']]={'system':observed(selector.get('kind','unknown'),[node['id']]),'numeric_value':observed(int(value),[node['id']]) if selector.get('kind')=='numeric' and value.isdigit() else unknown('not a numeric citation'),
            'first_appearance_rank':observed(seen[value],[node['id']]) if complete else unknown('incomplete citation extraction prevents ordinal judgment'),
            'is_first_use':observed(first,[node['id']]) if complete else unknown('earlier unobserved citations are possible')}
