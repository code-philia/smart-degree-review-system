import {expect,it} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {createTranslationService}=require('../src/normative/reportTranslationService');

it.each(['report','job'])('translates the whole abstract-comparison explanation for a %s while retaining original evidence',async kind=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'abstract-language-'));
  const source='随着软件系统深度融入社会关键基础设施，其内生安全已成为制约数字经济发展的核心瓶颈。';
  const message='英文摘要缺失：英文摘要未对应说明：'+source;
  const result={rule_runs:[{rule_id:'bilingual_abstract_consistency_check',findings:[{
    finding_id:'a',message,location:{text_excerpt:source},anchors:[{role:'source_span',label:'中文摘要原句',description:'中文摘要原句',location:{text_excerpt:source}}],
    evidence:[{kind:'source_span',quote:source}]
  }]}]};
  const before=JSON.stringify(result); const modelInputs=[];
  try {
    const translate=createTranslationService({cacheDir:root,loadReport:async()=>({result}),loadJob:async()=>({progress:result}),loadRepairs:async()=>[],
      model:async items=>{modelInputs.push(...items.map(i=>i.text));return {items:items.map(({id,text})=>({id,text:text.replace(/[\u3400-\u9fff]+/g,'English')}))};}});
    const response=await translate({userId:'owner',locale:'en',...(kind==='report'?{reportId:'r'}:{jobId:'j'})});
    expect(response.status).toBe('ready');
    expect(response.translations[message]).not.toMatch(/[\u3400-\u9fff]/);
    expect(modelInputs.some(text=>text.includes(source))).toBe(true);
    expect(JSON.stringify(result)).toBe(before);
  } finally {await fs.rm(root,{recursive:true,force:true});}
});
