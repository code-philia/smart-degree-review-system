import { File } from 'node:buffer';
import { expect,it } from 'vitest';
import apiClient from '../src/api';
import {runReviewPilotPaperLint} from '../src/api/paperLint';
it('sends a smaller gzip PDF body that decompresses to the original bytes',async()=>{
 const original='%PDF-1.7\n'+'论文测试数据。'.repeat(200000);const file=new File([original],'large.pdf',{type:'application/pdf'});
 let body:Blob|undefined;let encoding:unknown;
 const adapter=apiClient.defaults.adapter;
 apiClient.defaults.adapter=async config=>{body=config.data;encoding=config.headers.get('Content-Encoding');return {data:{job_id:'gzip-job',status:'pending'},status:202,statusText:'Accepted',headers:{},config};};
 try{const response=await runReviewPilotPaperLint(file,['sjtu_rule_31']);expect(response).toMatchObject({job_id:'gzip-job'});expect(encoding).toBe('gzip');expect(body!.size).toBeLessThan(file.size);const restored=await new Response(body!.stream().pipeThrough(new DecompressionStream('gzip'))).text();expect(restored).toBe(original);}
 finally{apiClient.defaults.adapter=adapter;}
});
