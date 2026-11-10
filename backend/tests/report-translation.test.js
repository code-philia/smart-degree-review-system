import { afterEach, beforeEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const service = require('../src/normative/reportTranslationService');
let root;
beforeEach(async () => { root = await fs.mkdtemp(path.join(os.tmpdir(),'report-translation-')); });
afterEach(async () => { await fs.rm(root,{recursive:true,force:true}); });
const explanation = '第 12 页的“原文 2.3”缺少对应说明。';
const report = () => ({ result: { paper_title:'原始论文题名', rule_runs:[{rule_id:'rule-1',message:'检测已完成',findings:[{
  finding_id:'finding-1', message:explanation, suggestion:'补充必要的说明。',
  location:{page_number:12,text_excerpt:'不可翻译原文'},evidence:[{text:'不可翻译证据'}],
  basis_details:[{text:'生成的判断依据'}],
}]}] } });
function options(overrides={}) { return {cacheDir:root,loadReport:async(id,user)=> user==='owner' ? report():null,
  loadRepairs:async()=>[{response:{actions:[{instruction:'核对后添加说明。'}],missing_context:['需要更多上下文']}}],
  model:async items=>({items:items.map(({id,text})=>({id,text:text.replace(/[\u3400-\u9fff]+/g,'English')}))}),
  ...overrides}; }
it('only extracts presentation fields including saved repairs without changing canonical data', async()=>{
  const original=report(), before=JSON.stringify(original);
  const texts=service.extractTexts(original.result,[{response:{actions:[{instruction:'核对修复建议'}],rationale:'原因说明',missing_context:['缺少上下文']}}]);
  expect(texts).toEqual(expect.arrayContaining([explanation,'补充必要的说明。','核对修复建议','原因说明','缺少上下文','生成的判断依据']));
  expect(texts).not.toEqual(expect.arrayContaining(['原始论文题名','不可翻译原文','不可翻译证据','rule-1','finding-1']));
  expect(JSON.stringify(original)).toBe(before);
});
it('protects quoted source and every numeric token, rejecting corruption and invented numbers',()=>{
  const protectedText=service.protectText(explanation);
  expect(protectedText.text).not.toContain('原文');
  expect(protectedText.text).not.toContain('12');
  const item={id:'i0',...protectedText};
  const good={items:[{id:'i0',text:'On page '+protectedText.text.match(/__P\d+__/g).join(' ')+' no description.'}]};
  expect(service.validateAnswer(good,[item])[0]).toContain('“原文 2.3”');
  expect(()=>service.validateAnswer({items:[{id:'i0',text:'English 99'}]},[item])).toThrow();
  expect(()=>service.validateAnswer({items:[{id:'extra',text:'English'}]},[item])).toThrow();
  expect(()=>service.validateAnswer({items:[...good.items,...good.items]},[item])).toThrow();
  expect(()=>service.validateAnswer({items:[{...good.items[0],text:good.items[0].text+' 99'}]},[item])).toThrow();
});
it('authorizes before persistent cache reads and reuses cache after a process restart',async()=>{
  let calls=0;
  const config=options({model:async items=>{calls++;return options().model(items);}});
  const translate=service.createTranslationService(config);
  const before=JSON.stringify(report());
  const first=await translate({reportId:'r',userId:'owner',locale:'en'});
  expect(first).toMatchObject({status:'ready',model:'qwen',locale:'en'});
  expect(first.translations[explanation]).toContain('“原文 2.3”');
  const second=await service.createTranslationService(config)({reportId:'r',userId:'owner',locale:'en'});
  expect(second).toEqual(first); expect(calls).toBe(1);
  await expect(translate({reportId:'r',userId:'other',locale:'en'})).rejects.toMatchObject({status:404});
  expect(JSON.stringify(report())).toBe(before);
});
it('dedupes concurrent translation of one owned revision',async()=>{
  let calls=0;
  const translate=service.createTranslationService(options({model:async items=>{
    calls++;await new Promise(resolve=>setTimeout(resolve,15));return options().model(items);
  }}));
  const [a,b]=await Promise.all([translate({reportId:'r',userId:'owner',locale:'en'}),translate({reportId:'r',userId:'owner',locale:'en'})]);
  expect(a).toEqual(b);expect(calls).toBe(1);
});
it('returns a partial subset on timeout and retries only uncached strings',async()=>{
  let calls=0, fail=true;
  const translate=service.createTranslationService(options({batchItems:2,maxBatches:10,model:async items=>{
    calls++;if(fail && calls===2)throw new Error('timeout');return options().model(items);
  }}));
  const first=await translate({reportId:'r',userId:'owner',locale:'en'});
  expect(first.status).toBe('partial');expect(Object.keys(first.translations)).toHaveLength(2);
  fail=false;const second=await translate({reportId:'r',userId:'owner',locale:'en'});
  expect(second.status).toBe('ready');expect(Object.keys(second.translations)).toHaveLength(6);
});
it('does not cache malformed output and lets a later request retry',async()=>{
  let bad=true,calls=0;
  const translate=service.createTranslationService(options({model:async items=>{
    calls++;return bad?{items:[{id:'invented',text:'English'}]}:options().model(items);
  }}));
  expect((await translate({reportId:'r',userId:'owner',locale:'en'})).status).toBe('unavailable');
  bad=false;expect((await translate({reportId:'r',userId:'owner',locale:'en'})).status).toBe('ready');
  expect(calls).toBe(2);
});
it('job ownership and completed report repairs use the same owner boundary',async()=>{
  const translate=service.createTranslationService(options({loadJob:async(id,user)=>user==='owner'?{progress:report().result,report_id:'r'}:null}));
  expect((await translate({jobId:'j',userId:'owner',locale:'en'})).status).toBe('ready');
  await expect(translate({jobId:'j',userId:'other',locale:'en'})).rejects.toMatchObject({status:404});
});
it('bounds work and returns partial until later requests fill the cache',async()=>{
  const translate=service.createTranslationService(options({batchItems:2,maxBatches:1}));
  const args={reportId:'r',userId:'owner',locale:'en'};
  expect((await translate(args)).status).toBe('partial');
  expect((await translate(args)).status).toBe('partial');
  expect((await translate(args)).status).toBe('ready');
});

it('extracts numeric explanations and diagnostics while preserving numeric source materials',()=>{
  const input={rule_runs:[{params:{preconditions:[{reason:'原因甲',suggestion:'建议甲'}],
    numeric_results:[{reason:'原因乙',suggestion:'建议乙',declaration:{text:'原论点'}}],
    contributions:[{text:'原贡献'}],mappings:[{chapter_title:'原章名',experiment_titles:['原实验名']}]},
    compiler_diagnostics:[{message:'诊断说明',reasons:['诊断原因'],basis_details:[{text:'判断依据'},{kind:'source_quote',text:'原文规范'}]}]}]};
  const texts=service.extractTexts(input);
  expect(texts).toEqual(expect.arrayContaining(['原因甲','建议甲','原因乙','建议乙','诊断说明','诊断原因','判断依据']));
  for(const source of ['原论点','原贡献','原章名','原实验名','原文规范'])expect(texts).not.toContain(source);
});
it('validates persisted entries before reuse and invalidates when source changes',async()=>{
  let version=0,calls=0;
  const config=options({loadReport:async()=>{const value=report();if(version)value.result.rule_runs[0].message='新增检测说明';return value;},
    model:async items=>{calls++;return options().model(items);}});
  const translate=service.createTranslationService(config),args={reportId:'r',userId:'owner',locale:'en'};
  const first=await translate(args);
  const folders=await fs.readdir(root);
  for(const folder of folders)for(const file of await fs.readdir(path.join(root,folder))){
    const target=path.join(root,folder,file),value=JSON.parse(await fs.readFile(target,'utf8'));
    value.text='Corrupted 999';await fs.writeFile(target,JSON.stringify(value));
  }
  expect((await translate(args)).status).toBe('ready');expect(calls).toBe(2);
  version=1;const updated=await translate(args);
  expect(updated.source_hash).not.toBe(first.source_hash);expect(calls).toBe(3);
});
it('bounds a genuinely stalled model subprocess and returns a retryable unavailable response',async()=>{
  const originalPython=process.env.REPORT_TRANSLATION_PYTHON;
  const originalTimeout=process.env.REPORT_TRANSLATION_TIMEOUT_MS;
  const shim=path.join(root,'python');
  await fs.writeFile(shim,'#!'+process.execPath+'\nprocess.stdin.resume();setInterval(()=>{},1000);\n',{mode:0o700});
  process.env.REPORT_TRANSLATION_PYTHON=shim;process.env.REPORT_TRANSLATION_TIMEOUT_MS='1000';
  const start=Date.now();
  try{
    const translate=service.createTranslationService(options({model:service.runModel}));
    const response=await translate({reportId:'r',userId:'owner',locale:'en'});
    expect(response.status).toBe('unavailable');expect(Date.now()-start).toBeLessThan(3000);
  }finally{
    for(const [key,value] of [['REPORT_TRANSLATION_PYTHON',originalPython],['REPORT_TRANSLATION_TIMEOUT_MS',originalTimeout]])
      if(value===undefined)delete process.env[key];else process.env[key]=value;
  }
},4000);

it('protects signed, scientific and percentage numeric values as complete literals',()=>{
  const item={id:'i0',...service.protectText('测得 -2.5e-3、+8、−4 和 99.1%。')};
  expect(item.tokens).toEqual(['-2.5e-3','+8','−4','99.1%']);
  const translated=service.validateAnswer({items:[{id:'i0',text:'Measured '+item.text.match(/__P\d+__/g).join(', ')+'.'}]},[item])[0];
  expect(translated).toContain('-2.5e-3');
});
it('never claims ready when source has reserved markers or oversized prose',async()=>{
  for(const text of ['原始内容 __P0__', '需要说明'.repeat(2001)]){
    const translate=service.createTranslationService(options({loadReport:async()=>({result:{rule_runs:[{message:text}]}}),loadRepairs:async()=>[]}));
    const response=await translate({reportId:'special',userId:'owner',locale:'en'});
    expect(response.status).toBe('unavailable');expect(Object.keys(response.translations)).toHaveLength(0);
  }
});
it('caps global translation subprocesses so repeated distinct reports cannot create an unbounded worker queue',async()=>{
  const original=process.env.REPORT_TRANSLATION_PYTHON;
  const shim=path.join(root,'python-cap');
  await fs.writeFile(shim,'#!'+process.execPath+'\nlet value="";process.stdin.on("data",x=>value+=x);process.stdin.on("end",()=>setTimeout(()=>{process.stdout.write(JSON.stringify({items:JSON.parse(value).items.map(({id})=>({id,text:"Explanation."}))}));},150));\n',{mode:0o700});
  process.env.REPORT_TRANSLATION_PYTHON=shim;
  try{
    const translate=service.createTranslationService(options({model:undefined,loadRepairs:async()=>[],
      loadReport:async id=>({result:{rule_runs:[{message:'原因'+id}]}})}));
    const results=await Promise.all(['甲','乙','丙'].map(reportId=>translate({reportId,userId:'owner',locale:'en'})));
    expect(results.map(result=>result.status).sort()).toEqual(['ready','ready','unavailable']);
  }finally{if(original===undefined)delete process.env.REPORT_TRANSLATION_PYTHON;else process.env.REPORT_TRANSLATION_PYTHON=original;}
});

it('includes custom anchor presentation labels without collecting anchor source locations',()=>{
  const texts=service.extractTexts({rule_runs:[{findings:[{anchors:[{
    label:'自定义中文证据标签',description:'定位说明',location:{text_excerpt:'原文不可翻译'}
  }]}],params:{numeric_results:[{abstract_anchors:[{label:'摘要侧证据'}],evidence_anchors:[{
    label:'实验侧证据',location:{text_excerpt:'实验原文不可翻译'}
  }]}]}}]});
  expect(texts).toEqual(expect.arrayContaining(['自定义中文证据标签','定位说明','摘要侧证据','实验侧证据']));
  expect(texts).not.toContain('原文不可翻译');expect(texts).not.toContain('实验原文不可翻译');
});

it('preserves authoritative standard and project basis clauses as original source',()=>{
  const texts=service.extractTexts({rule_runs:[{findings:[{basis_details:[
    {kind:'standard',text:'标准原文不得翻译'},
    {kind:'project',text:'项目规则原文不得翻译'},
    {kind:'explanation',text:'模型生成的说明可以翻译'}
  ]}]}]});
  expect(texts).toContain('模型生成的说明可以翻译');
  expect(texts).not.toContain('标准原文不得翻译');
  expect(texts).not.toContain('项目规则原文不得翻译');
});

it.each([
  ['inconsistent','论点与论据不一致'],
  ['inconclusive','论据不明确'],
])('includes exact derived numeric %s finding prose after page-claim sanitization',async(status,prefix)=>{
  const value={rule_runs:[{rule_id:'abstract_numeric_consistency_check',findings:[],params:{
    preconditions:[{passed:true}],numeric_results:[{declaration_id:'d1',status,
      reason:'D1:A1在第12页与摘要数值不一致。',suggestion:'请核对原始实验数据。',
      evidence:[{candidate_id:'D1:A1'}],abstract_anchors:[{anchor_id:'abstract',location:{text_excerpt:'摘要原文'}}],
      evidence_anchors:[{anchor_id:'D1:A1',location:{text_excerpt:'实验原文'}}]
    }]
  }}]};
  const before=JSON.stringify(value);
  const expected=prefix+'：实验结果证据1在与摘要数值不一致。';
  expect(service.extractTexts(value)).toContain(expected);
  expect(service.extractTexts(value)).toContain('实验结果证据1');
  expect(service.extractTexts(value)).not.toContain('摘要原文');
  const translate=service.createTranslationService(options({loadJob:async()=>({progress:value}),loadRepairs:async()=>[]}));
  const response=await translate({jobId:'live',userId:'owner',locale:'en'});
  expect(response.status).toBe('ready');expect(response.translations).toHaveProperty(expected);
  expect(JSON.stringify(value)).toBe(before);
});
it('collects shared derived reference notices for raw live job progress',()=>{
  const result={rule_runs:[{rule_id:'sjtu_rule_32',findings:[],compiler_diagnostics:[
    {status:'UNKNOWN',check_id:'reference_lookup',node_id:'entry1',reasons:['NO_MATCH'],evidence:[]}
  ]}]};
  expect(service.extractTexts(result)).toContain('引用核验证据不足，请人工核查。');
  expect(service.extractTexts(result)).toContain('请核对参考文献的题名、作者、年份和 DOI；未检索到充分证据不表示文献不存在。');
});

it.each(['疑似错字：','疑似错别字：','疑似错别字:'])('preserves the entire explicit typo source after %s including multiline context',prefix=>{
  const target='一个CVE\n漏洞在代码层面往可能涉及多个函数';
  const item={id:'i0',...service.protectText(prefix+target)};
  expect(item.tokens).toEqual([target]);
  const output=service.validateAnswer({items:[{id:'i0',text:'Suspected typo: __P0__'}]},[item])[0];
  expect(output).toBe('Suspected typo: '+target);
});
it('rejects old cached translated-away typo targets and regenerates with source placeholders',async()=>{
  const {createHash}=require('crypto');
  const original='疑似错字：揭示';
  const key=createHash('sha256').update(JSON.stringify(['owner',original,'en','qwen',
    process.env.REPORT_TRANSLATION_MODEL||'qwen',process.env.REPORT_TRANSLATION_MODEL_VERSION||'campus-current',service.PROMPT_VERSION])).digest('hex');
  const file=path.join(root,key.slice(0,2),key+'.json');
  await fs.mkdir(path.dirname(file),{recursive:true});
  await fs.writeFile(file,JSON.stringify({key,text:'Suspected typo: Reveal'}));
  let calls=0;
  const translate=service.createTranslationService(options({loadReport:async()=>({result:{rule_runs:[{
    rule_id:'typo_detection_check',findings:[{message:original}]
  }]}}),loadRepairs:async()=>[],model:async items=>{calls++;return {items:items.map(({id})=>({id,text:'Suspected typo: __P0__'}))};}}));
  const response=await translate({reportId:'typo',userId:'owner',locale:'en'});
  expect(response.status).toBe('ready');expect(response.translations[original]).toBe('Suspected typo: 揭示');expect(calls).toBe(1);
});
it('keeps schema-defined typo corrections and source-span descriptions literal while translating explanations',async()=>{
  const source='一个CVE\n漏洞在代码层面往可能涉及多个函数',correction='往往';
  const value={rule_runs:[{rule_id:'typo_detection_check',findings:[{
    message:'疑似错别字：'+source,suggestion:correction,reason:'错别字，应为“往往”',
    location:{text_excerpt:source},anchors:[{role:'source_span',label:'疑似错别字',description:source,location:{text_excerpt:source}}],
    evidence:[{kind:'source_span',quote:source}]
  }]}]};
  const before=JSON.stringify(value);const inputs=[];
  const translate=service.createTranslationService(options({loadReport:async()=>({result:value}),loadRepairs:async()=>[],
    model:async items=>{inputs.push(...items.map(item=>item.text));return options().model(items);}}));
  const response=await translate({reportId:'typo',userId:'owner',locale:'en'});
  expect(response.status).toBe('ready');
  expect(response.translations['疑似错别字：'+source]).toContain(source);
  expect(response.translations[correction]).toBe(correction);
  expect(response.translations[source]).toBe(source);
  expect(inputs.some(text=>text.includes(source)||text.includes(correction))).toBe(false);
  expect(JSON.stringify(value)).toBe(before);
});
it('protects exact same-finding source fields in prose and separates cache by source provenance',async()=>{
  const original='请核对检测结果字段。';let hasSource=true,calls=0;
  const translate=service.createTranslationService(options({loadReport:async()=>({result:{rule_runs:[{findings:[{
    message:original,...(hasSource?{location:{text_excerpt:'检测结果'}}:{})
  }]}]}}),loadRepairs:async()=>[],model:async items=>{calls++;return options().model(items);}}));
  const first=await translate({reportId:'r',userId:'owner',locale:'en'});
  expect(first.translations[original]).toContain('检测结果');
  hasSource=false;const second=await translate({reportId:'r',userId:'owner',locale:'en'});
  expect(second.translations[original]).not.toContain('检测结果');
  expect(second.source_hash).not.toBe(first.source_hash);expect(calls).toBe(2);
});
it('does not treat general issue or suggestion prefixes as source-literal heuristics',()=>{
  for(const value of ['疑似错误：计算服务暂不可用。','建议：重新核对实验说明。']){
    const protectedText=service.protectText(value);
    expect(protectedText.tokens).toEqual([]);expect(protectedText.text).toBe(value);
  }
});

it('invalidates old typo cache even if old numeric masking has the same placeholder count',async()=>{
  const {createHash}=require('crypto');
  const original='疑似错字：揭示12';
  const key=createHash('sha256').update(JSON.stringify(['owner',original,'en','qwen',
    process.env.REPORT_TRANSLATION_MODEL||'qwen',process.env.REPORT_TRANSLATION_MODEL_VERSION||'campus-current',service.PROMPT_VERSION])).digest('hex');
  const file=path.join(root,key.slice(0,2),key+'.json');
  await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,JSON.stringify({key,text:'Suspected typo: Reveal __P0__'}));
  let calls=0;
  const translate=service.createTranslationService(options({loadReport:async()=>({result:{rule_runs:[{findings:[{message:original}]}]}}),
    loadRepairs:async()=>[],model:async items=>{calls++;return {items:items.map(({id})=>({id,text:'Suspected typo: __P0__'}))};}}));
  const response=await translate({reportId:'typo-numeric',userId:'owner',locale:'en'});
  expect(response.translations[original]).toBe('Suspected typo: 揭示12');expect(calls).toBe(1);
});

it('translates source-span abstract UI descriptions while retaining exact source excerpts',async()=>{
  const labels=['中文摘要原句','英文摘要原句','中文摘要','英文摘要'];
  const value={rule_runs:[{rule_id:'bilingual_abstract_consistency_check',findings:[{
    message:'中文摘要原句与英文摘要原句存在差异，原文为“保留论文原文”。',
    anchors:labels.map((label,index)=>({role:'source_span',label,description:label,
      location:{text_excerpt:index%2?'英文原始材料':'保留论文原文'}})),
    evidence:[{kind:'source_span',quote:'保留论文原文'}]
  }]}]};
  const before=JSON.stringify(value),protections=service.extractLiteralProtections(value);
  for(const label of labels)expect(protections.has(label)).toBe(false);
  const translate=service.createTranslationService(options({loadReport:async()=>({result:value}),loadRepairs:async()=>[]}));
  const response=await translate({reportId:'bilingual-labels',userId:'owner',locale:'en'});
  expect(response.status).toBe('ready');
  for(const label of labels)expect(response.translations[label]).toBe('English');
  expect(response.translations[value.rule_runs[0].findings[0].message]).toContain('“保留论文原文”');
  expect(JSON.stringify(value)).toBe(before);
});
it('uses the versioned bilingual omission glossary prompt cache',()=>{
  expect(service.PROMPT_VERSION).toBe('report-presentation-en-v2');
});
