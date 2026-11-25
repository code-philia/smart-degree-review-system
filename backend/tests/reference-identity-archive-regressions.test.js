import { createRequire } from 'node:module';
import { afterEach, expect, it, vi } from 'vitest';
const require=createRequire(import.meta.url);
const core=require('../src/normative/referenceVerificationCore');
const title='Reliable evidence for scholarly reference identity';
const cited=extra=>({title,authors:['SMITH J','DOE R'],year:2023,type_code:'J',extraction_confidence:'high',...extra});
const crossref=extra=>({DOI:'10.1234/example',title:[title],author:[{given:'John',family:'Smith'},{given:'Richard',family:'Doe'}],published:{'date-parts':[[2023]]},type:'journal-article',...extra});
function atom({id='2301.01234v2',heading=title,authors=['John Smith','Richard Doe'],published=2023,updated=published}={}){
 return new Response(`<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/${id}</id><title>${heading}</title>${authors.map(name=>`<author><name>${name}</name></author>`).join('')}<published>${published}-01-01T00:00:00Z</published><updated>${updated}-03-01T00:00:00Z</updated></entry></feed>`);
}
function fixture(handler){
 const requests=[];
 const fetchImpl=async(input,init)=>{const url=new URL(input);requests.push({url,init});const result=handler(url,init);if(result!==undefined)return result;
  if(url.hostname==='api.openalex.org')return url.pathname==='/works'?Response.json({results:[]}):Response.json({},{status:404});
  if(url.hostname==='api.crossref.org')return url.pathname==='/works'?Response.json({message:{items:[]}}):Response.json({},{status:404});
  if(url.hostname==='api.datacite.org')return url.pathname==='/dois'?Response.json({data:[]}):Response.json({},{status:404});
  if(url.hostname==='export.arxiv.org')return new Response('<feed></feed>');
  return new Response('',{status:503});
 };
 return {personalKey:'test-personal-key',fetchImpl,requests,crossrefScheduler:core.createCrossrefScheduler()};
}
afterEach(()=>vi.useRealTimers());
async function timed(c, f){vi.useFakeTimers();const pending=core.verifyReference(c,f);await vi.runAllTimersAsync();return pending;}

it('combines Crossref main title and subtitle before comparing the full citation',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:crossref({title:['LOF'],subtitle:['Identifying density-based local outliers']})}):undefined);
 const r=await core.verifyReference(cited({doi:'10.1234/example',title:'LOF: Identifying density-based local outliers'}),f);
 expect(r.category).toBe('verified');expect(r.matched.title).toBe('LOF: Identifying density-based local outliers');
});
it('prefers a fully corroborating exact DOI record over another catalog missing its subtitle',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json({id:'https://openalex.org/W12',title:'LOF',doi:'https://doi.org/10.1234/example',publication_year:2023,type:'article',authorships:[{author:{display_name:'John Smith'}}]}):u.hostname==='api.crossref.org'?Response.json({message:crossref({title:['LOF'],subtitle:['Identifying density-based local outliers']})}):undefined);
 const r=await core.verifyReference(cited({doi:'10.1234/example',title:'LOF: Identifying density-based local outliers'}),f);
 expect(r.category).toBe('verified');expect(r.matched.provider).toBe('crossref');
});
it('does not accept an unrelated full title merely because the DOI resolves',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:crossref({title:['An unrelated scholarly work']})}):undefined);
 expect((await core.verifyReference(cited({doi:'10.1234/example'}),f)).category).toBe('mismatch');
});
it('matches equivalent Unicode and LaTeX superscript notation',async()=>{
 const heading='τ²-Bench: Evaluating Conversational Agents in a Dual-Control Environment';
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:crossref({title:['$\\tau^2$-Bench: Evaluating Conversational Agents in a Dual-Control Environment']})}):undefined);
 expect((await core.verifyReference(cited({doi:'10.1234/example',title:heading}),f)).category).toBe('verified');
});
it('matches a surname transliteration without removing meaningful name letters',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:crossref({author:[{given:'Mirosław',family:'Kutyłowski'}]})}):undefined);
 expect((await core.verifyReference(cited({doi:'10.1234/example',authors:['KUTYLOWSKI M']}),f)).category).toBe('verified');
});
it('recognizes a leading organization followed by the cited ordered personal authors',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({authors:['OpenAI','John Smith','Richard Doe']}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234'}),f)).category).toBe('verified');
});
it('recognizes a colon-delimited organization heading before personal authors',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({authors:['ResearchLab',':','John Smith','Richard Doe']}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234'}),f)).category).toBe('verified');
});
it('does not skip a genuine first personal author to find a convenient later author',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({authors:['Alice Brown','John Smith','Richard Doe']}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234'}),f)).category).toBe('mismatch');
});
it('does not guess that a camel-cased single surname is an organization',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({authors:['McDonald','John Smith','Richard Doe']}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234'}),f)).category).toBe('mismatch');
});
it('retains a real first-author initial mismatch for an exact arXiv work',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({authors:['Ryan Murtfeldt','Richard Doe']}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234',authors:['MURTFELDT P','DOE R']}),f)).category).toBe('mismatch');
});
it('uses the documented arXiv revision year as equivalent evidence',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({published:2017,updated:2019}):undefined);
 const r=await core.verifyReference(cited({arxiv_id:'2301.01234',year:2019}),f);
 expect(r.category).toBe('verified');expect(r.comparisons.find(c=>c.field==='year').status).toBe('equivalent');
});
it('still rejects a year absent from the authoritative arXiv version dates',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({published:2017,updated:2019}):undefined);
 expect((await core.verifyReference(cited({arxiv_id:'2301.01234',year:2031}),f)).category).toBe('mismatch');
});
it('checks a historical arXiv version when its current title has changed',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({id:u.searchParams.get('id_list')?.endsWith('v1')?'2301.01234v1':'2301.01234v3',heading:u.searchParams.get('id_list')?.endsWith('v1')?title:'A new title for the same research',published:2023,updated:2025}):undefined);
 const r=await timed(cited({arxiv_id:'2301.01234'}),f);
 expect(r.category).toBe('verified');expect(r.matched.title).toBe(title);
 expect(f.requests.filter(r=>r.url.hostname==='export.arxiv.org').map(r=>r.url.searchParams.get('id_list'))).toEqual(['2301.01234','2301.01234v1']);
});
it('does not turn a fabricated historical title into a verified record',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({id:u.searchParams.get('id_list')?.endsWith('v1')?'2301.01234v1':'2301.01234v2',heading:'The actual title of a different citation'}):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234'}),f)).category).toBe('mismatch');
});
it('does not blame a renamed preprint title when the historical version cannot be retrieved',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?(u.searchParams.get('id_list')?.endsWith('v1')?new Response('',{status:503}):atom({heading:'The revised title of the same preprint'})):undefined);
 const r=await timed(cited({arxiv_id:'2301.01234'}),f);
 expect(r.category).toBe('unverified');expect(r.comparisons.find(c=>c.field==='title').status).toBe('unknown');
});
it('retains a real title mismatch when the authoritative current record is already v1',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?(u.searchParams.get('id_list')?.endsWith('v1')?new Response('',{status:404}):atom({id:'2301.01234v1',heading:'The actual title of the first version'})):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234'}),f)).category).toBe('mismatch');
 expect(f.requests.filter(r=>r.url.hostname==='export.arxiv.org')).toHaveLength(1);
});
it('uses an explicitly cited arXiv version without silently substituting v1 or latest',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom({id:'2301.01234v2'}):undefined);
 const r=await core.verifyReference(cited({arxiv_id:'2301.01234v2'}),f);
 expect(r.category).toBe('verified');expect(f.requests.find(r=>r.url.hostname==='export.arxiv.org').url.searchParams.get('id_list')).toBe('2301.01234v2');
});
it('never verifies an explicit arXiv version using only versionless discovery metadata',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json({results:[{id:'https://openalex.org/W12',title,publication_year:2023,ids:{arxiv:'2301.01234'},authorships:[{author:{display_name:'John Smith'}}],type:'article'}]}):u.hostname==='export.arxiv.org'?new Response('',{status:404}):undefined);
 const r=await core.verifyReference(cited({arxiv_id:'2301.01234v9'}),f);
 expect(r.category).toBe('unverified');expect(r.comparisons.filter(c=>c.field==='arxiv_id'&&c.status==='match')).toHaveLength(0);
});
it('does not verify an unfound extra arXiv identifier merely because its separate DOI resolves',async()=>{
 const f=fixture(u=>u.hostname==='api.crossref.org'?Response.json({message:crossref()}):u.hostname==='export.arxiv.org'?new Response('',{status:404}):undefined);
 expect((await timed(cited({doi:'10.1234/example',arxiv_id:'2301.01234'}),f)).category).toBe('unverified');
});
it.each(['0','1000'])('does not silently replace explicit arXiv v%s with the latest version',async version=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():undefined);
 const r=await timed(cited({arxiv_id:`2301.01234v${version}`}),f);
 expect(r.category).toBe('unverified');
 expect(f.requests.filter(r=>r.url.hostname==='export.arxiv.org').every(r=>r.url.searchParams.get('id_list')===`2301.01234v${version}`)).toBe(true);
});
it('does not compare the publication year of a later article against its cited preprint',async()=>{
 const f=fixture(u=>u.hostname==='api.openalex.org'?Response.json({results:[{id:'https://openalex.org/W12',title,publication_year:2026,doi:'https://doi.org/10.1234/published',ids:{arxiv:'2301.01234'},authorships:[{author:{display_name:'John Smith'}}],type:'article'}]}):u.hostname==='export.arxiv.org'?new Response('',{status:503}):u.hostname==='api.datacite.org'&&u.pathname.includes('10.48550')?Response.json({data:{id:'10.48550/arxiv.2301.01234',attributes:{doi:'10.48550/arxiv.2301.01234',titles:[{title}],creators:[{name:'John Smith'}],publicationYear:2023,types:{resourceTypeGeneral:'Preprint'}}}}):undefined);
 const r=await timed(cited({arxiv_id:'2301.01234',authors:['SMITH J']}),f);
 expect(r.category).toBe('verified');expect(r.matched.year).toBe(2023);expect(r.matched.doi).toBe('10.48550/arxiv.2301.01234');
});
const ris=(year=1987,doi='10.1007/3-540-47721-7_12')=>new Response(`TY  - CHAP\nTI  - ${title}\nAU  - Smith, John\nAU  - Doe, Richard\nPY  - ${year}\nDO  - ${doi}\nER  - \n`,{headers:{'content-type':'application/x-research-info-systems'}});
function datedFixture(response){return fixture(u=>u.hostname==='api.openalex.org'?Response.json({id:'https://openalex.org/W12',title,doi:'https://doi.org/10.1007/3-540-47721-7_12',publication_year:2007,type:'book-chapter',authorships:[{author:{display_name:'John Smith'}}]}):u.hostname==='api.crossref.org'?Response.json({message:crossref({DOI:'10.1007/3-540-47721-7_12',published:undefined,type:'book-chapter'})}):u.hostname==='citation-needed.springer.com'?response():undefined);}
it('resolves conflicting electronic and print years using the publisher citation record',async()=>{
 const f=datedFixture(()=>ris());const r=await timed(cited({doi:'10.1007/3-540-47721-7_12',year:1987}),f);
 expect(r.category).toBe('verified');expect(r.matched.year).toBe(1987);
 expect(f.requests.some(r=>r.url.hostname==='citation-needed.springer.com'&&r.url.searchParams.get('format')==='refman')).toBe(true);
});
it('keeps an actual incorrect print year as a mismatch after publisher verification',async()=>{
 const f=datedFixture(()=>ris());expect((await timed(cited({doi:'10.1007/3-540-47721-7_12',year:1975}),f)).category).toBe('mismatch');
});
it('does not accept a publisher record for a different DOI',async()=>{
 const f=datedFixture(()=>ris(1987,'10.1007/different'));expect((await timed(cited({doi:'10.1007/3-540-47721-7_12',year:1987}),f)).category).not.toBe('verified');
});
it('keeps uncertain old-book dates unverified when the publisher is unavailable',async()=>{
 const f=datedFixture(()=>new Response('',{status:503}));const r=await timed(cited({doi:'10.1007/3-540-47721-7_12',year:1987}),f);
 expect(r.category).toBe('unverified');expect(r.comparisons.find(c=>c.field==='year').status).toBe('unknown');
});
it('verifies a collective author only when the same arXiv document header confirms it',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<html><meta name="citation_arxiv_id" content="2301.01234v1"><h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_personname">Research Team</span></div><div class="ltx_abstract">Abstract</div></html>`):undefined);
 const r=await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f);
 expect(r.category).toBe('verified');expect(r.matched.authors).toEqual(['Research Team']);
});
it('allows a slow metadata header within the existing total reference deadline',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Promise(resolve=>setTimeout(()=>resolve(new Response(`<h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_personname">Research Team</span></div>`)),6000)):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('verified');
});
it('stops reading once the author header is complete instead of waiting for a slow full article',async()=>{
 let cancelled=false;
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(new ReadableStream({
  start(controller){controller.enqueue(new TextEncoder().encode(`<h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_personname">Research Team</span></div>`));},
  cancel(){cancelled=true;},
 })):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('verified');
 expect(cancelled).toBe(true);
});
it('keeps a hung collective-author header bounded and unverified',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Promise(()=>{}):undefined);
 const started=Date.now(),r=await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f);
 expect(r.category).toBe('unverified');expect(Date.now()-started).toBeLessThanOrEqual(18000);
});
it('never treats a group name mentioned in references as a collective author',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_personname">John Smith</span></div><section class="ltx_bibliography">Research Team</section>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('unverified');
});
it('does not accept an arXiv HTML header for a different identifier',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<meta name="citation_arxiv_id" content="2302.99999"><h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_personname">Research Team</span></div>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).not.toBe('verified');
});
it('reads only the document author block inside a normal outer HTML wrapper',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<div id="page"><h1 class="ltx_title ltx_title_document">${title}</h1><div class="ltx_authors"><span class="ltx_creator"><span class="ltx_personname">Research Team</span></span></div></div>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('verified');
});
it.each(['<!-- %s -->','<script>const ignored="%s";</script>','<textarea>%s</textarea>'])('ignores inert author markup in %s',async inert=>{
 const fake='<div class="ltx_authors"><span class="ltx_personname">Research Team</span></div>';
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<h1 class="ltx_title ltx_title_document">${title}</h1>${inert.replace('%s',fake)}<div class="ltx_authors"><span class="ltx_personname">John Smith</span></div>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('unverified');
});
it('does not treat data-class attributes as author metadata classes',async()=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<h1 class="ltx_title ltx_title_document">${title}</h1><div data-class="ltx_authors"><span data-class="ltx_personname">Research Team</span></div><div class="ltx_authors"><span class="ltx_personname">John Smith</span></div>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('unverified');
});
it.each(['div','article'])('ignores author markup inside a quoted attribute on %s',async tag=>{
 const f=fixture(u=>u.hostname==='export.arxiv.org'?atom():u.hostname==='arxiv.org'?new Response(`<h1 class="ltx_title ltx_title_document">${title}</h1><${tag} data-note="<div class='ltx_authors'><span class='ltx_personname'>Research Team</span></div>"></${tag}><div class="ltx_authors"><span class="ltx_personname">John Smith</span></div>`):undefined);
 expect((await timed(cited({arxiv_id:'2301.01234',authors:['Research Team']}),f)).category).toBe('unverified');
});
it('rejects publisher identity fields placed after the RIS end-of-record marker',async()=>{
 const f=datedFixture(()=>new Response(`TY  - CHAP\nER  -\nTI  - ${title}\nAU  - Smith, John\nPY  - 1987\nDO  - 10.1007/3-540-47721-7_12\n`));
 expect((await timed(cited({doi:'10.1007/3-540-47721-7_12',year:1987}),f)).category).toBe('unverified');
});
