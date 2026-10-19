"""Work identity is separate from identifier correctness and search success."""
import re
import unicodedata
from urllib.parse import urlsplit

IDENTITY_POLICY = 'source-backed-arxiv-url-pin/1.4'
from difflib import SequenceMatcher

def normalize_doi(value):
    value=str(value or '').strip()
    return re.sub(r'^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)', '', value, flags=re.I).casefold()

def _work_dois(work):
    aliases=work.get('doi_aliases',[])
    values=[work.get('doi','')]+(aliases if isinstance(aliases,list) else [])
    return {normalize_doi(value) for value in values if normalize_doi(value)}

def _arxiv_identifier(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    doi = normalize_doi(value)
    match = re.fullmatch(r'10\.48550/arxiv\.(\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?)', doi)
    if match:
        return match.group(1)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {'http', 'https'} or parsed.hostname not in
                {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'} or parsed.username or parsed.password or
                parsed.port not in {None, 80, 443}):
            return None
    except ValueError:
        return None
    match = re.fullmatch(r'/(?:abs|pdf)/(\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?', parsed.path)
    return match.group(1).lower() if match else None


def _work_arxiv_identifiers(work):
    return {identifier for value in [*_work_dois(work), work.get('url')]
            if (identifier := _arxiv_identifier(value)) is not None}


def _norm(text):return ''.join(c for c in unicodedata.normalize('NFKC',str(text)).casefold() if c.isalnum())
def _author_match(left,right):
    def variants(name):
        words=re.findall(r'[a-z]+',unicodedata.normalize('NFKD',str(name)).casefold())
        if len(words)==1:return [(words[0],'','',True)]
        if not words:return []
        result=[]
        for family,given in [(words[0],words[1:]),(words[-1],words[:-1])]:
            initials=''.join(w if len(w)<=2 else w[0] for w in given)
            result.append((family,''.join(given),initials,all(len(w)<=2 for w in given)))
        return result
    for a in left:
        for b in right:
            if _norm(a) and _norm(a)==_norm(b):return True
            for family,given,initials,abbreviated in variants(a):
                for other,first,other_initials,other_abbreviated in variants(b):
                    if family!=other or len(family)<2:continue
                    if not given or not first or given==first or ((abbreviated or other_abbreviated) and initials==other_initials):return True
    return False


def _explicit_subtitle_supported(entry, work):
    """Accept omitted subtitles only with exact main title and independent metadata."""
    left = unicodedata.normalize('NFKC', str(entry.get('title', '')))
    right = unicodedata.normalize('NFKC', str(work.get('title', '')))
    expanded, plain = (left, right) if ':' in left and ':' not in right else (right, left)
    if ':' not in expanded or ':' in plain:
        return False
    main, subtitle = expanded.split(':', 1)
    if not subtitle.strip() or len(_norm(main)) < 24 or _norm(main) != _norm(plain):
        return False
    authors = entry.get('authors', [])
    other = work.get('authors', [])
    # One coinciding surname is not sufficient for this additional acceptance path.
    if (not isinstance(authors, list) or not isinstance(other, list) or
            len({_norm(a) for a in authors if _norm(a)}) < 2):
        return False
    remaining = list(other)
    for author in authors:
        matching = next((i for i, candidate in enumerate(remaining)
                         if _author_match([author], [candidate])), None)
        if matching is None:
            return False
        remaining.pop(matching)
    return entry.get('year') is not None and str(entry['year']) == str(work.get('year'))

def resolve_identity(entry:dict,records:list[dict],client=None)->dict:
    candidates=[];title=_norm(entry.get('title',''))
    for r in records:
        if r.get('status')!='ok' or not isinstance(r.get('work'),dict):continue
        work=r['work'];other=_norm(work.get('title',''))
        author=_author_match(entry.get('authors',[]),work.get('authors',[]))
        year=entry.get('year') is not None and str(entry['year'])==str(work.get('year'))
        doi=bool(normalize_doi(entry.get('doi'))) and normalize_doi(entry.get('doi')) in _work_dois(work)
        similarity=SequenceMatcher(None,title,other).ratio() if title and other else 0
        author_conflict=bool(entry.get('authors')) and bool(work.get('authors')) and not author
        year_conflict=entry.get('year') is not None and work.get('year') is not None and not year
        decisive=len(title)>=12 and similarity>=.96 and not author_conflict and not year_conflict and ((author and year) or doi)
        candidates.append((r,author,year,doi,similarity,decisive))
    matches=[c for c in candidates if c[-1]]
    if not matches and client:
        possible=[c for c in candidates if c[1] and c[2]]
        if possible:
            from .llm import ModelError
            try:
                answer=client.complete_json('work-identity/1.0', 'Decide whether a candidate describes the same work. Return same_work:boolean,candidate_id:string,reason:string,title_relation:string,author_supported:boolean,year_supported:boolean. A translated title may match with independent author and year support. A similar topic alone cannot. Never claim nonexistence.', {'entry':entry,'candidates':[{'id':c[0]['id'],'work':c[0]['work']} for c in possible]},1200)
            except ModelError as error:
                return {'state':'unknown','reason':'optional identity model unavailable: '+type(error).__name__+': '+str(error),
                        'evidence_ids':[record['id'] for record in records]}
            chosen=[c for c in possible if c[0]['id']==answer.get('candidate_id')]
            relation = answer.get('title_relation')
            relation_supported = relation in {'translation','same','minor_variation'}
            if relation in {'shortened_title', 'shortened_title_match', 'translated_or_variant'}:
                relation_supported = bool(chosen) and all(
                    _explicit_subtitle_supported(entry, c[0]['work']) for c in chosen)
            if answer.get('same_work') is True and relation_supported and answer.get('author_supported') is True and answer.get('year_supported') is True:
                matches=chosen
    if matches:
        exact=[c for c in matches if c[3]]
        source_arxiv = _arxiv_identifier(entry.get('url'))
        url_exact = [c for c in matches if source_arxiv and source_arxiv in _work_arxiv_identifiers(c[0]['work'])]
        # A primary arXiv identity is stronger than an aggregate's alias to a
        # distinct conference DOI. Do not merge the conference into the preprint.
        url_primary = [c for c in url_exact if source_arxiv in {
            _arxiv_identifier(c[0]['work'].get('doi')), _arxiv_identifier(c[0]['work'].get('url'))}]
        if url_primary:
            url_exact = url_primary
        if exact:
            if url_exact and not any(c in url_exact for c in exact):
                return {'state':'unknown','reason':'conflicting explicit DOI and arXiv URL identities',
                        'evidence_ids':[c[0]['id'] for c in matches]}
            matches=exact
        elif url_exact:
            matches=url_exact
        identities={(_norm(c[0]['work'].get('title','')),normalize_doi(c[0]['work'].get('doi',''))) for c in matches}
        # Several inconsistent records are ambiguous, even if their names look similar.
        nonempty_dois={x[1] for x in identities if x[1]}
        if len(nonempty_dois)>1 and not exact:return {'state':'unknown','reason':'multiple conflicting work identities','evidence_ids':[c[0]['id'] for c in matches]}
        openalex_ids={c[0]['work'].get('openalex_id') for c in matches if c[0]['work'].get('openalex_id')}
        if len(openalex_ids)>1:return {'state':'unknown','reason':'multiple conflicting OpenAlex work identities','evidence_ids':[c[0]['id'] for c in matches]}
        selected=max(matches,key=lambda c:(c[3],c[4],bool(c[0]['work'].get('abstract'))));work=dict(selected[0]['work'])
        ids=[c[0]['id'] for c in matches];work['evidence_ids']=ids
        repositories={c[0]['work'].get('pmcid') for c in matches if re.fullmatch(r'PMC\d+',str(c[0]['work'].get('pmcid',''))) and c[0]['work'].get('doi','').lower()==work.get('doi','').lower() and work.get('doi')}
        if len(repositories)==1:work['pmcid']=repositories.pop()
        # Merge corroborated optional fields only when their nonempty values agree.
        field_sources={}
        for field in ['container','volume','issue','pages','publisher','place','institution','version']:
            supplied=[(c[0]['id'],c[0]['work'][field],c[0]['work'].get('field_provenance',{}).get(field)) for c in matches if c[0]['work'].get(field)]
            values={str(v).strip() for _,v,_ in supplied}
            if len(values)==1:
                work[field]=supplied[0][1];field_sources[field]=[{'evidence_id':eid,'provider_field':path} for eid,_,path in supplied]
            elif len(values)>1:work.pop(field,None)
        work['field_sources']=field_sources
        conflicts=[]
        if entry.get('doi') and work.get('doi') and normalize_doi(entry['doi']) not in _work_dois(work):conflicts.append('doi')
        return {'state':'observed','value':True,'evidence_ids':ids,'work':work,'metadata_conflicts':conflicts,'method':'source_backed_arxiv_url' if url_exact and not exact else 'corroborated_metadata'}
    return {'state':'unknown','reason':'public retrieval does not establish or exclude this work','evidence_ids':[r['id'] for r in records]}
