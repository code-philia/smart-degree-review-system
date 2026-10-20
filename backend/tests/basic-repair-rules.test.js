import {expect,it} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const {buildPaperLintReportRepairRequest,RULE_TEXT}=require('../src/normative/legacyRepairAdapter');const {buildMessages}=require('../src/normative/repairModelProposalService');
function build(limit){return buildPaperLintReportRepairRequest({report:{id:'report',result:{}},documentSha256:'a'.repeat(64),ruleRun:{rule_id:'chinese_abstract_length_check',params:{max_chars:limit}},finding:{finding_id:'long-abstract',message:'摘要超过长度上限',anchors:[]}});}
it('binds actual basic-check parameters to the repair cache and passes them to the model',()=>{const first=build(1000),next=build(1500);expect(first.source_identity_sha256).not.toBe(next.source_identity_sha256);expect(JSON.parse(buildMessages(first)[1].content).rule.parameters).toEqual({max_chars:1000});});
it('labels an unlocated detector assertion as a record rather than PDF text',()=>{const request=build(1000);expect(request.evidence[0].source_kind).toBe('retrieval');expect(request.evidence[0].text).toContain('不是 PDF 原文');expect(RULE_TEXT.required_section_completeness_check).toContain('核心章节');});
