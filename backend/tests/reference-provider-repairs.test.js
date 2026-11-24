import { createRequire } from 'node:module';
import { afterEach, expect, it, vi } from 'vitest';
const require=createRequire(import.meta.url);
const core=require('../src/normative/referenceVerificationCore');
const title='Reliable metadata verification for scholarly references';
const entry=extra=>({title,authors:['Smith, J.'],year:2023,type_code:'J',extraction_confidence:'high',...extra});
const oa=extra=>({id:'https://openalex.org/W123',title,publication_year:2023,doi:'https://doi.org/10.1234/reliable',type:'article',authorships:[{author:{display_name:'John Smith'}}],...extra});
const cr=extra=>({DOI:'10.1234/reliable',title:[title],author:[{given:'John',family:'Smith'}],published:{'date-parts':[[2023]]},type:'journal-article',...extra});
const dc=(doi,heading=title,name='John Smith',year=2023)=>({id:doi,type:'dois',attributes:{doi,titles:[{title:heading}],creators:[{name}],publicationYear:year,types:{resourceTypeGeneral:'ConferencePaper'},relatedIdentifiers:[]}});
function fixture(handler){
 const requests=[];
 const fetchImpl=async(input,init)=>{const u=new URL(input);requests.push({url:u,at:Date.now()});const result=handler?.(u,init);if(result!==undefined)return result;
  if(u.hostname==='api.openalex.org')return u.pathname==='/works'?Response.json({results:[]}):Response.json({}, {status:404});
  if(u.hostname==='api.crossref.org')return u.pathname==='/works'?Response.json({message:{items:[]}}):Response.json({}, {status:404});
  if(u.hostname==='api.datacite.org')return u.pathname==='/dois'?Response.json({data:[]}):Response.json({}, {status:404});
  throw new Error('Unexpected provider');};
 return {personalKey:'fixture-personal',fetchImpl,requests,crossrefScheduler:core.createCrossrefScheduler?.()};
}
afterEach(()=>vi.useRealTimers());

it('accepts legacy SICI DOI characters and constructs encoded fixed-host links',async()=>{
 const doi='10.1002/(sici)1097-0118(199903)30:3<213::aid-jgt6>3.0.co;2-#';
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:cr({DOI:doi})}):undefined);
 const value=await core.verifyReference(entry({doi}),f);
 expect(value.category).toBe('verified');expect(value.matched.doi).toBe(doi);
 expect(value.matched.url).toContain('%3C');expect(value.matched.url).toContain('%23');
 expect(new URL(value.matched.url).hostname).toBe('doi.org');expect(new URL(value.matched.url).hash).toBe('');
});
it('keeps valid candidates when another Crossref row is malformed',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:{items:[{},cr()]}}):undefined);
 const value=await core.verifyReference(entry(),f);
 expect(value.category).toBe('incomplete');expect(value.matched.doi).toBe('10.1234/reliable');
 expect(value.sources.find(s=>s.provider==='crossref').status).toBe('success');
});
it('keeps a wholly malformed nonempty Crossref list unavailable rather than treating it as an empty search',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:{items:[{},null]}}):undefined);
 const value=await core.verifyReference(entry(),f);
 expect(value.category).toBe('unverified');expect(value.sources.find(s=>s.provider==='crossref').status).toBe('unavailable');
});

it('serializes public Crossref queries at one per second across references without queue-induced entry timeouts',async()=>{
 vi.useFakeTimers();let active=0,maxActive=0;
 const f=fixture(async u=>{if(u.hostname!=='api.crossref.org')return u.hostname==='api.openalex.org'?Response.json({results:[]}):Response.json({data:[]});
  active++;maxActive=Math.max(maxActive,active);await new Promise(r=>setTimeout(r,50));active--;return Response.json({message:{items:[]}});});
 const pending=Promise.all(Array.from({length:25},(_,i)=>core.verifyReference(entry({title:title+' '+i}),f)));
 await vi.advanceTimersByTimeAsync(26000);const values=await pending;
 const starts=f.requests.filter(r=>r.url.hostname==='api.crossref.org').map(r=>r.at);
 expect(starts).toHaveLength(25);expect(starts.slice(1).every((at,i)=>at-starts[i]>=1000)).toBe(true);expect(maxActive).toBe(1);
 expect(values.every(v=>v.sources.find(s=>s.provider==='crossref').status==='not_found')).toBe(true);
});
it('limits public DOI requests to five per second and shares the same single provider slot',async()=>{
 vi.useFakeTimers();let active=0,maxActive=0;
 const f=fixture(async u=>{if(u.hostname!=='api.crossref.org')return Response.json({}, {status:404});active++;maxActive=Math.max(maxActive,active);
  await new Promise(r=>setTimeout(r,50));active--;return Response.json({message:cr({DOI:decodeURIComponent(u.pathname.slice(7))})});});
 const pending=Promise.all(Array.from({length:8},(_,i)=>core.verifyReference(entry({doi:'10.1234/item-'+i}),f)));
 await vi.advanceTimersByTimeAsync(4000);await pending;
 const starts=f.requests.filter(r=>r.url.hostname==='api.crossref.org').map(r=>r.at);
 expect(starts).toHaveLength(8);expect(starts.slice(1).every((at,i)=>at-starts[i]>=200)).toBe(true);expect(maxActive).toBe(1);
});
it('cancels a queued Crossref request promptly and releases following work',async()=>{
 vi.useFakeTimers();let release,calls=0;
 const controller=new AbortController();
 const f=fixture(u=>u.hostname==='api.crossref.org'?++calls===1?new Promise(r=>{release=()=>r(Response.json({message:{items:[]}}));}):Response.json({message:{items:[]}}):undefined);
 const first=core.verifyReference(entry(),f);await vi.advanceTimersByTimeAsync(0);
 const queued=core.verifyReference(entry({title:title+' cancelled'}),{...f,signal:controller.signal});
 const assertion=expect(queued).rejects.toMatchObject({name:'AbortError'});controller.abort();await assertion;
 const following=core.verifyReference(entry({title:title+' following'}),f);
 release();await vi.advanceTimersByTimeAsync(1000);await Promise.all([first,following]);
 expect(f.requests.filter(r=>r.url.hostname==='api.crossref.org')).toHaveLength(2);
});
it('honors Retry-After on Crossref before a bounded retry',async()=>{
 vi.useFakeTimers();let calls=0;
 const f=fixture(u=>u.hostname==='api.crossref.org'?++calls===1?Response.json({}, {status:429,headers:{'retry-after':'2'}}):Response.json({message:{items:[cr()]}}):undefined);
 const pending=core.verifyReference(entry(),f);await vi.advanceTimersByTimeAsync(1999);expect(calls).toBe(1);
 await vi.advanceTimersByTimeAsync(10000);const value=await pending;expect(calls).toBe(2);expect(value.category).toBe('incomplete');
});
it('backs off exponentially on DOI service failures, stops after three attempts and reports the real failure',async()=>{
 vi.useFakeTimers();
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({}, {status:503}):undefined);
 const pending=core.verifyReference(entry({doi:'10.1234/unavailable'}),f);await vi.advanceTimersByTimeAsync(5000);const value=await pending;
 const starts=f.requests.filter(r=>r.url.hostname==='api.crossref.org').map(r=>r.at);
 expect(starts).toHaveLength(3);expect(starts[1]-starts[0]).toBe(500);expect(starts[2]-starts[1]).toBe(1000);
 expect(value.sources.find(s=>s.provider==='crossref').status).toBe('unavailable');expect(value.category).toBe('unverified');
});

const title10='Homomorphism-Distinguishing Closedness for Graphs of Bounded Tree-Width';
const formal10='10.4230/lipics.stacs.2024.53';
it('prefers the exact cited DataCite publication over an OpenAlex preprint DOI',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json(u.pathname==='/works'?{results:[oa({title:title10,doi:'https://doi.org/10.26092/elib/4267',publication_year:2023,ids:{arxiv:'https://arxiv.org/abs/2304.07011'},authorships:[{author:{display_name:'Daniel Neuen'}}]})]}:oa({title:title10,doi:'https://doi.org/10.26092/elib/4267',publication_year:2023,ids:{arxiv:'https://arxiv.org/abs/2304.07011'},authorships:[{author:{display_name:'Daniel Neuen'}}]}))
  :u.hostname==='api.datacite.org'?Response.json({data:dc(formal10,title10,'Neuen, Daniel',2024)}):undefined);
 const value=await core.verifyReference(entry({title:title10,authors:['NEUEN D'],year:2024,doi:formal10,type_code:'C'}),f);
 expect(value.category).toBe('verified');expect(value.matched.doi).toBe(formal10);expect(value.matched.year).toBe(2024);
 expect(f.requests.some(r=>r.url.hostname==='api.datacite.org'&&decodeURIComponent(r.url.pathname)==='/dois/'+formal10)).toBe(true);
});
it('abstains when only a same-title preprint with a different DOI is found and the cited DOI cannot be resolved',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json(u.pathname==='/works'?{results:[oa({doi:'https://doi.org/10.48550/arxiv.2301.01234',type:'preprint'})]}:oa({doi:'https://doi.org/10.48550/arxiv.2301.01234',type:'preprint'})):undefined);
 const value=await core.verifyReference(entry({doi:'10.4230/lipics.stacs.2024.53'}),f);
 expect(value.category).toBe('unverified');expect(value.reason_code).toBe('identifier_unresolved');
});
it('still reports a genuine cited DOI whose authoritative title and first author are different',async()=>{
 const doi='10.4230/lipics.stacs.2024.53';
 const f=fixture(u=>u.hostname==='api.datacite.org'?Response.json({data:dc(doi,'A wholly unrelated geological analysis','Another, Person',2023)}):undefined);
 const value=await core.verifyReference(entry({doi}),f);
 expect(value.category).toBe('mismatch');expect(value.reason_code).toBe('metadata_conflict');
});
const title12='An Algorithmic Meta Theorem for Homomorphism Indistinguishability';
it('recovers the MFCS2024 publication via bounded exact-title DataCite search with matching first author and year',async()=>{
 const repository=dc('10.18154/rwth-2024-07911',title12,'Seppelt, Tim Frederik',2024);repository.attributes.types={resourceTypeGeneral:'Text'};
 const f=fixture(u=>u.hostname==='api.datacite.org'?Response.json({data:[repository,dc('10.48550/arxiv.2402.08989',title12,'Seppelt, Tim',2024),dc('10.4230/lipics.mfcs.2024.82',title12,'Seppelt, Tim',2024)]}):undefined);
 const value=await core.verifyReference(entry({title:title12,authors:['SEPPELT T'],year:2024,type_code:'C'}),f);
 expect(value.category).toBe('incomplete');expect(value.matched.doi).toBe('10.4230/lipics.mfcs.2024.82');
 const query=f.requests.find(r=>r.url.hostname==='api.datacite.org').url;
 expect(query.pathname).toBe('/dois');expect(query.searchParams.get('page[size]')).toBe('5');expect(query.searchParams.get('query')).toContain('titles.title:');
});
it('looks for the corroborated conference edition when an otherwise matching preprint is returned first',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json({results:[oa({title:title12,publication_year:2024,doi:'https://doi.org/10.48550/arxiv.2402.08989',type:'preprint',authorships:[{author:{display_name:'Tim Seppelt'}}]})]})
  :u.hostname==='api.datacite.org'?Response.json({data:[dc('10.4230/lipics.mfcs.2024.82',title12,'Seppelt, Tim',2024)]}):undefined);
 const value=await core.verifyReference(entry({title:title12,authors:['SEPPELT T'],year:2024,type_code:'C'}),f);
 expect(value.category).toBe('incomplete');expect(value.matched.doi).toBe('10.4230/lipics.mfcs.2024.82');
});
it('rejects a DataCite singleton whose DOI does not equal the requested citation',async()=>{
 const f=fixture(u=>u.hostname==='api.datacite.org'?Response.json({data:dc('10.1234/another')}):undefined);
 const value=await core.verifyReference(entry({doi:'10.4230/lipics.stacs.2024.53'}),f);
 expect(value.category).toBe('unverified');expect(value.sources.find(s=>s.provider==='datacite').status).toBe('unavailable');
});
it.each([['Wrong, Person',2024],['Seppelt, Tim',2020]])('does not verify a DataCite title-only candidate with author=%s and year=%s',async(name,year)=>{
 const f=fixture(u=>u.hostname==='api.datacite.org'?Response.json({data:[dc('10.4230/lipics.mfcs.2024.82',title12,name,year)]}):undefined);
 const value=await core.verifyReference(entry({title:title12,authors:['SEPPELT T'],year:2024,type_code:'C'}),f);
 expect(value.category).toBe('unverified');
});

const wrappedCases=[
 {label:'reference7',raw:'Quantum and non-signalling graph iso- morphisms',joined:'Quantum and non-signalling graph isomorphisms',author:'ATSERIAS A',catalogAuthor:'Albert Atserias',year:2019,doi:'10.1016/j.jctb.2018.11.002'},
 {label:'reference16',raw:'Limitations of Game Comonads for Invertible-Map Equiv- alence via Homomorphism Indistinguishability',joined:'Limitations of Game Comonads for Invertible-Map Equivalence via Homomorphism Indistinguishability',author:'LICHTER M',catalogAuthor:'Moritz Lichter',year:2024,doi:'10.4230/lipics.csl.2024.36'},
];
it.each(wrappedCases)('matches native-attested softwrap metadata for $label while preserving the original cited title',async c=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:{items:[cr({DOI:c.doi,title:[c.joined],author:[{name:c.catalogAuthor}],published:{'date-parts':[[c.year]]}})]}}):undefined);
 const value=await core.verifyReference(entry({title:c.raw,title_search_variants:[c.joined],authors:[c.author],year:c.year}),f);
 expect(value.category).toBe('incomplete');expect(value.matched.doi).toBe(c.doi);
 expect(value.comparisons.find(row=>row.field==='title')).toMatchObject({cited:c.raw,matched:c.joined,status:'match'});
});
it.each(wrappedCases)('uses a bounded free catalog fallback for $label when the literal broken title cannot be retrieved',async c=>{
 vi.useFakeTimers();
 const f=fixture(u=>u.hostname==='api.crossref.org'&&u.searchParams.get('query.bibliographic')===c.joined
  ?Response.json({message:{items:[cr({DOI:c.doi,title:[c.joined],author:[{name:c.catalogAuthor}],published:{'date-parts':[[c.year]]}})]}}):undefined);
 const pending=core.verifyReference(entry({title:c.raw,title_search_variants:[c.joined],authors:[c.author],year:c.year}),f);
 await vi.advanceTimersByTimeAsync(5000);const value=await pending;
 expect(value.category).toBe('incomplete');expect(value.matched.doi).toBe(c.doi);
 expect(f.requests.filter(row=>row.url.hostname==='api.crossref.org').map(row=>row.url.searchParams.get('query.bibliographic'))).toEqual([c.raw,c.joined]);
 expect(f.requests.some(row=>row.url.hostname==='serpapi.com')).toBe(false);
});
it.each([['Another Author',2019],['Albert Atserias',2010]])('keeps author/year guards for a valid softwrap variant (%s, %s)',async(name,year)=>{
 vi.useFakeTimers();const c=wrappedCases[0];
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:{items:[cr({DOI:c.doi,title:[c.joined],author:[{name}],published:{'date-parts':[[year]]}})]}}):undefined);
 const pending=core.verifyReference(entry({title:c.raw,title_search_variants:[c.joined],authors:[c.author],year:c.year}),f);
 await vi.advanceTimersByTimeAsync(5000);expect((await pending).category).toBe('unverified');
});
it('rejects unrelated injected title variants and variants beyond the two-candidate bound',async()=>{
 const c=wrappedCases[0],unrelated='An unrelated geological measurement source';
 const f=fixture();
 const value=await core.verifyReference(entry({title:c.raw,title_search_variants:[unrelated,null,c.joined],authors:[c.author],year:c.year}),f);
 expect(value.matched).toBeNull();
 expect(f.requests.some(row=>[...row.url.searchParams.values()].some(value=>value.includes(unrelated)||value.includes(c.joined)))).toBe(false);
});
it('keeps a real DOI conflict even when a native softwrap title variant matches another publication',async()=>{
 vi.useFakeTimers();const c=wrappedCases[0];
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:u.pathname==='/works'
  ?{items:[cr({DOI:c.doi,title:[c.joined],author:[{name:c.catalogAuthor}],published:{'date-parts':[[c.year]]}})]}
  :cr({DOI:'10.1234/wrong',title:['A completely unrelated geological measurement study'],author:[{name:'Someone Else'}],published:{'date-parts':[[c.year]]}})}):undefined);
 const pending=core.verifyReference(entry({title:c.raw,title_search_variants:[c.joined],authors:[c.author],year:c.year,doi:'10.1234/wrong'}),f);
 await vi.advanceTimersByTimeAsync(5000);const value=await pending;
 expect(value.category).toBe('mismatch');expect(value.reason_code).toBe('identifier_conflict');
});
it('does not repeat a paid SerpAPI lookup for softwrap variants or enable anonymous OpenAlex for SerpAPI-only access',async()=>{
 vi.useFakeTimers();const c=wrappedCases[0];
 const f=fixture(u=>u.hostname==='serpapi.com'?Response.json({organic_results:[]}):undefined);
 const pending=core.verifyReference(entry({title:c.raw,title_search_variants:[c.joined],authors:[c.author],year:c.year}),{...f,personalKey:null,serpapiKey:'fixture-personal-serp'});
 await vi.advanceTimersByTimeAsync(5000);await pending;
 expect(f.requests.filter(row=>row.url.hostname==='serpapi.com')).toHaveLength(1);
 expect(f.requests.some(row=>row.url.hostname==='api.openalex.org')).toBe(false);
});
