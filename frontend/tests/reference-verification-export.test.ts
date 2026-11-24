import {expect,it} from 'vitest';
import {buildExportReport,reportText} from '../src/utils/reportExport/model';
import {localizeExportReport} from '../src/utils/reportExport/presentation';
const row={category:'mismatch',entry:{id:'r1',text:'[1] Smith. Reliable source. 2024.',title:'Reliable source',year:2024},matched:{title:'Reliable source',year:2023},comparisons:[{field:'year',cited:2024,matched:2023,status:'different'}],sources:[{provider:'crossref',url:'https://doi.org/10.1234/example',status:'ok'}],coverage:{complete:true}};
const report:any={id:'r',source_filename:'paper.pdf',created_at:'2026-11-25',selected_rule_ids:['reference_verification_check'],result:{paper_title:'paper',ruleset:{name:'reference',version_label:'reference/1'},rule_runs:[{rule_id:'reference_verification_check',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'f1',rule_id:'reference_verification_check',message:'信息不符：Reliable source',message_en:'Metadata mismatch: Reliable source',suggestion:'请核对年份。',suggestion_en:'Check the year.',reference_check:row,evidence:[]}],params:{reference_verification:{entries:[row]}}}],summary:{}}};
it('exports actual metadata comparison and provider source in both languages',()=>{
 const model=buildExportReport(report,[{rule_id:'reference_verification_check',title:'参考文献真实性核验',description:''}] as any,null);
 expect(reportText(model)).toContain('2023');expect(reportText(model)).toContain('https://doi.org/10.1234/example');
 const english=localizeExportReport(model,'en');
 expect(english.findings[0].message).toBe('Metadata mismatch: Reliable source');
 expect(english.findings[0].suggestions).toContain('Check the year.');
 expect(reportText(english)).toContain('Year');
});
