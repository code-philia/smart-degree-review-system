"""Identity-bound public metadata fixtures for direct R31 sandbox checks."""
import re

TYPES={'journal_article':'journal-article','conference':'proceedings-article','book_chapter':'book-chapter','preprint':'preprint'}

def bind_type(analysis,node_id,text,kind,*,year,year_start):
    assert text[year_start:year_start+4]==year
    fields=analysis['results']['bibliography_fields'][node_id]
    fields['year']={'state':'observed','value':year,'source_range':[year_start,year_start+4],'evidence_ids':[node_id]}
    eid='metadata-type-'+node_id
    work={'title':fields['title']['value'],'authors':['AUTHOR A'],'year':int(year),'type':TYPES[kind]}
    container=fields.get('container',{})
    span=container.get('source_range',[])
    if container.get('state')=='observed' and len(span)==2 and text[span[0]:span[1]]==container.get('value'):
        work['container']=container['value']
    doi=re.search(r'10\.\d{4,9}/[^\s<>]+',text)
    if doi:work['doi']=doi.group(0).rstrip('.。,，;；)）]］')
    locator=re.search(r'arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)',text)
    if locator and not doi:
        work['doi']='10.48550/arXiv.'+locator.group(1)
        work['url']='https://arxiv.org/abs/'+locator.group(1)
    analysis.setdefault('evidence',[]).append({'id':eid,'provider':'fixture_public_catalog','status':'ok',
        'coverage':'partial_index','work':work})
    analysis['results'].setdefault('external_work',{}).setdefault(node_id,{})['exists']={
        'state':'observed','value':True,'evidence_ids':[eid]}
