import type {PaperLintRuleRun} from '../../api/paperLint';
import type {ReportBlock} from './model';
import {presentationBlock} from './presentation';
const categories:Record<string,[string,string]>={verified:['已核验','Verified'],suspected:['疑似伪造','Suspected fabrication'],mismatch:['信息不符','Metadata mismatch'],upgrade:['可升级','Published version available'],incomplete:['可补全','Can be completed'],unverified:['未核验','Unverified']};
const fields:Record<string,[string,string]>={title:['题名','Title'],authors:['作者','Authors'],year:['年份','Year'],doi:['DOI','DOI'],arxiv_id:['arXiv','arXiv']};
const text=(v:unknown)=>Array.isArray(v)?v.map(String).join(', '):v===undefined||v===null?'—':String(v);
export function referenceReportBlocks(run:PaperLintRuleRun):ReportBlock[]{
 if(run.rule_id!=='reference_verification_check')return [];
 const data=run.params?.reference_verification as {entries?:Array<Record<string,any>>}|undefined;
 const blocks:ReportBlock[]=[];
 for(const row of data?.entries || []){
  const category=categories[row.category] || categories.unverified;
  const title=text(row.entry?.title || row.entry?.text);
  blocks.push(presentationBlock({kind:'subheading',text:`${category[0]}：${title}`},()=>`${category[1]}: ${title}`,[]));
  if(row.entry?.text)blocks.push({kind:'quote',text:row.entry.text});
  for(const comparison of row.comparisons || []){
   const field=fields[comparison.field] || [comparison.field,comparison.field];
   const cited=text(comparison.cited),matched=text(comparison.matched);
   blocks.push(presentationBlock({kind:'text',text:`${field[0]}：引用 ${cited}；数据库 ${matched}`},()=>`${field[1]}: cited ${cited}; database ${matched}`,[]));
  }
  for(const source of row.sources || []){
   let url;try{url=new URL(source.url);}catch{continue;}
   if(!['https:','http:'].includes(url.protocol)||url.username||url.password)continue;
   blocks.push({kind:'text',text:`${source.provider}: ${url.href} (${source.status})`});
  }
  if(row.category==='suspected'||row.category==='unverified')blocks.push(presentationBlock({kind:'notice',text:'检索未匹配不代表文献不存在，请人工复核。'},()=> 'A search miss does not prove nonexistence. Review the source manually.',[]));
 }
 return blocks;
}
