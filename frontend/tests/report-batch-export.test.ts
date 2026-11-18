import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {Blob as NodeBlob} from 'node:buffer';
import {unzipSync, strFromU8} from 'fflate';
import {createBatchReportFile} from '../src/utils/reportExport/batch';
import {fetchPaperLintReport, fetchPaperLintDocumentMetrics, fetchReviewPilotPaperLintRules} from '../src/api/paperLint';
import {fetchPaperLintRepairSuggestionHistory} from '../src/api/repairSuggestions';
import {createReportFile} from '../src/utils/reportExport/formats';
import {fixture} from './fixtures/reportExport';
vi.mock('../src/api/paperLint',()=>({fetchPaperLintReport:vi.fn(),fetchPaperLintDocumentMetrics:vi.fn(),fetchReviewPilotPaperLintRules:vi.fn()}));
vi.mock('../src/api/repairSuggestions',()=>({fetchPaperLintRepairSuggestionHistory:vi.fn()}));
vi.mock('../src/utils/reportExport/formats',()=>({createReportFile:vi.fn()}));
beforeEach(()=>{
  vi.stubGlobal('Blob', NodeBlob);
  vi.clearAllMocks();
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({rules:[]} as any);
  vi.mocked(fetchPaperLintReport).mockImplementation(async id=>({...fixture,id,source_filename:'同名论文.pdf'}));
  vi.mocked(fetchPaperLintDocumentMetrics).mockResolvedValue({page_count:7,word_count:20,text_available:true} as any);
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockResolvedValue([]);
  vi.mocked(createReportFile).mockImplementation(async model=>({filename:'同名报告.txt',blob:new Blob([model.report_id])}));
});
afterEach(()=>vi.unstubAllGlobals());
it('exports every selected saved report in order, deduplicates IDs and prevents duplicate filenames in the ZIP',async()=>{
  const progress=vi.fn(); const file=await createBatchReportFile(['one','two','one'],'text',{locale:'zh',onProgress:progress});
  const entries=unzipSync(new Uint8Array(await file.blob.arrayBuffer()));
  expect(Object.keys(entries)).toEqual(['001_同名报告.txt','002_同名报告.txt']);
  expect(Object.values(entries).map(strFromU8)).toEqual(['one','two']);
  expect(fetchPaperLintReport).toHaveBeenCalledTimes(2);
  expect(fetchReviewPilotPaperLintRules).toHaveBeenCalledTimes(1);
  expect(progress).toHaveBeenLastCalledWith({completed:2,total:2});
  expect(file.filename).toMatch(/\.zip$/);
});
it('includes latest saved suggestions and metrics without requesting new suggestions',async()=>{
  const response={schema_version:'repair-response-v2',status:'suggested',actions:[{instruction:'已保存的新建议',evidence_ids:[]}]} as any;
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockResolvedValue([
    {finding_id:'f1',generation:2,response},
    {finding_id:'f1',generation:1,response:{...response,actions:[{instruction:'过期建议',evidence_ids:[]}]}}
  ] as any);
  await createBatchReportFile(['one'],'text',{locale:'en'});
  const [model,format,options]=vi.mocked(createReportFile).mock.calls[0];
  expect(JSON.stringify(model)).toContain('已保存的新建议');
  expect(JSON.stringify(model)).not.toContain('过期建议');
  expect(model.document.page_count).toBe(7); expect(format).toBe('text');expect(options?.locale).toBe('en');
});
it('processes one report at a time and stops after a report fails',async()=>{
  vi.mocked(createReportFile).mockRejectedValueOnce(new Error('render failed'));
  await expect(createBatchReportFile(['one','two'],'pdf',{locale:'zh'})).rejects.toThrow(/同名论文.*render failed/);
  expect(fetchPaperLintReport).toHaveBeenCalledTimes(1);
});
it('honors cancellation during a saved-report read without rendering or moving to another report',async()=>{
  const controller=new AbortController();
  vi.mocked(fetchPaperLintReport).mockImplementation(async id=>{controller.abort();return {...fixture,id};});
  await expect(createBatchReportFile(['one','two'],'pdf',{locale:'zh',signal:controller.signal})).rejects.toMatchObject({name:'AbortError'});
  expect(createReportFile).not.toHaveBeenCalled();expect(fetchPaperLintReport).toHaveBeenCalledTimes(1);
});
it('rejects an oversized archive before reading its large file into memory',async()=>{
  const arrayBuffer=vi.fn();vi.mocked(createReportFile).mockResolvedValue({filename:'large.pdf',blob:{size:129*1024*1024,arrayBuffer} as any});
  await expect(createBatchReportFile(['one'],'pdf',{locale:'en'})).rejects.toThrow(/128 MB/);
  expect(arrayBuffer).not.toHaveBeenCalled();
});
it('does not start any reads when already cancelled or given an empty selection',async()=>{
  const controller=new AbortController();controller.abort();
  await expect(createBatchReportFile(['one'],'text',{signal:controller.signal})).rejects.toMatchObject({name:'AbortError'});
  await expect(createBatchReportFile([],'text')).rejects.toThrow();
  expect(fetchReviewPilotPaperLintRules).not.toHaveBeenCalled();
});
