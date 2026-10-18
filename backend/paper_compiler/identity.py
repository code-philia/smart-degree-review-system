"""Work identity is separate from identifier correctness and search success."""
import re
import unicodedata
from difflib import SequenceMatcher

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

def resolve_identity(entry:dict,records:list[dict],client=None)->dict:
    candidates=[];title=_norm(entry.get('title',''))
    for r in records:
        if r.get('status')!='ok' or not isinstance(r.get('work'),dict):continue
        work=r['work'];other=_norm(work.get('title',''))
        author=_author_match(entry.get('authors',[]),work.get('authors',[]))
        year=entry.get('year') is not None and str(entry['year'])==str(work.get('year'))
        doi=bool(entry.get('doi')) and entry['doi'].lower()==work.get('doi','').lower()
        similarity=SequenceMatcher(None,title,other).ratio() if title and other else 0
        author_conflict=bool(entry.get('authors')) and bool(work.get('authors')) and not author
        year_conflict=entry.get('year') is not None and work.get('year') is not None and not year
        decisive=len(title)>=12 and similarity>=.96 and not author_conflict and not year_conflict and ((author and year) or doi)
        candidates.append((r,author,year,doi,similarity,decisive))
    matches=[c for c in candidates if c[-1]]
    if not matches and client:
        possible=[c for c in candidates if c[1] and c[2]]
        if possible:
            answer=client.complete_json('work-identity/1.0', 'Decide whether a candidate describes the same work. Return same_work:boolean,candidate_id:string,reason:string,title_relation:string,author_supported:boolean,year_supported:boolean. A translated title may match with independent author and year support. A similar topic alone cannot. Never claim nonexistence.', {'entry':entry,'candidates':[{'id':c[0]['id'],'work':c[0]['work']} for c in possible]},1200)
            chosen=[c for c in possible if c[0]['id']==answer.get('candidate_id')]
            if answer.get('same_work') is True and answer.get('title_relation') in {'translation','same','minor_variation'} and answer.get('author_supported') is True and answer.get('year_supported') is True:
                matches=chosen
    if matches:
        exact=[c for c in matches if c[3]]
        if exact:matches=exact
        identities={(_norm(c[0]['work'].get('title','')),c[0]['work'].get('doi','')) for c in matches}
        # Several inconsistent records are ambiguous, even if their names look similar.
        nonempty_dois={x[1] for x in identities if x[1]}
        if len(nonempty_dois)>1:return {'state':'unknown','reason':'multiple conflicting work identities','evidence_ids':[c[0]['id'] for c in matches]}
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
        if entry.get('doi') and work.get('doi') and entry['doi'].lower()!=work['doi'].lower():conflicts.append('doi')
        return {'state':'observed','value':True,'evidence_ids':ids,'work':work,'metadata_conflicts':conflicts,'method':'corroborated_metadata'}
    return {'state':'unknown','reason':'public retrieval does not establish or exclude this work','evidence_ids':[r['id'] for r in records]}
