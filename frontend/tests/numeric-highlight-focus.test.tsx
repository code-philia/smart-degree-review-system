import { afterEach, beforeEach, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { numericHighlightTerms, refineNumericAnnotations } from '../src/components/paperLint/numericHighlight';
import { PdfOverlay } from '../src/components/paperLint/PdfOverlay';
import type { PaperLintPdfAnnotation } from '../src/components/paperLint/geometry';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
import { addTranslations, clearTranslations, setLocale } from '../src/i18n/locale';

const rule='abstract_numeric_consistency_check';
const bounds={x1:20,y1:100,x2:500,y2:300,width:595,height:842,page_number:4};
function annotation(terms=['3.57']):PaperLintPdfAnnotation {
  return {findingKey:'one',ruleId:rule,severity:'info',pageNumber:4,boundingRect:bounds,rects:[bounds],anchorId:'abstract-d1',focusTerms:terms};
}
function item():PaperLintFindingItem {
  return {key:'one',index:0,finding:{finding_id:rule+'_d1',rule_id:rule,message:''},ruleRun:{
    rule_id:rule,rule_run_id:'r',severity:'info',execution_status:'completed',outcome:'inconclusive',findings:[],params:{numeric_results:[{
      declaration_id:'d1',declaration:{number:'3.57',unit:'m'},
      reason:'声明称三个区域的平均误差为3.57 m、3.69 m和3.62 m。主证据d1:t1（表5-1，第53页）显示空旷区为3.57 m及3.73 m，与摘要一致。其他区域3.69 m和4.01 m未核实。',
      evidence:[{candidate_id:'d1:t1',quote:'空旷区均值3.57、3.73；中位数3.38、3.62。'}],
    }]}}};
}
const originalRange=Object.getOwnPropertyDescriptor(Range.prototype,'getClientRects');
beforeEach(()=>{
  setLocale('zh'); clearTranslations();
  Object.defineProperty(Range.prototype,'getClientRects',{configurable:true,value:function(this:Range){
    const parent=this.startContainer.parentElement!;
    const scale=Number(parent.dataset.scale||1);
    const left=100+(Number(parent.dataset.x||30)+this.startOffset*5)*scale;
    const top=200+Number(parent.dataset.y||120)*scale;
    return [{left,top,right:left+(this.endOffset-this.startOffset)*5*scale,bottom:top+12*scale,width:(this.endOffset-this.startOffset)*5*scale,height:12*scale}];
  }});
});
afterEach(()=>{
  setLocale('zh'); clearTranslations();
  if(originalRange) Object.defineProperty(Range.prototype,'getClientRects',originalRange);
  else delete (Range.prototype as any).getClientRects;
});
function page(content:string,scale=1){
  const element=document.createElement('div');
  element.innerHTML=`<div class="textLayer">${content}</div>`;
  element.getBoundingClientRect=()=>({left:100,top:200,width:595*scale,height:842*scale,right:100+595*scale,bottom:200+842*scale,x:100,y:200,toJSON(){}});
  document.body.append(element);
  return element;
}

it('takes only the selected claim values and removes technical source/page numbers',()=>{
  const terms=numericHighlightTerms(item(),{anchor_id:'abstract-d1',role:'source_span',location:{type:'pdf_page',page_number:4}});
  expect(terms).toEqual(expect.arrayContaining(['3.57','3.69','3.62']));
  expect(terms).not.toContain('53');
  expect(terms).not.toContain('1');
});
it('uses the exact evidence reference rather than the rest of the finding',()=>{
  const terms=numericHighlightTerms(item(),{anchor_id:'d1:t1',role:'source_span',location:{type:'pdf_page',page_number:53}});
  expect(terms).toEqual(expect.arrayContaining(['3.57','3.73']));
  expect(terms).not.toContain('3.69');
  expect(terms).not.toContain('4.01');
  expect(terms).not.toContain('53');
});
it('does not highlight a claimed value that the evidence description explicitly says is absent',()=>{
  const finding=item();
  const row=(finding.ruleRun.params!.numeric_results as any[])[0];
  row.declaration={number:'5.53',unit:'%',metric:'gAUC相对提升'};
  row.reason='声明称gAUC提升5.53%。主证据d1:t1提到DIN的gAUC提升4.99%，也未出现5.53%。';
  row.evidence=[{candidate_id:'d1:t1',quote:'和5.53%；同时，DIN的gAUC提升4.99%。'}];
  finding.finding.message='论点与论据不一致：实验结果证据1提到DIN的gAUC提升4.99%，也未出现5.53%。';
  expect(numericHighlightTerms(finding,{anchor_id:'d1:t1',location:{page_number:53}} as any)).toEqual(['4.99']);
});
it('uses the same visible evidence fallback while English translation is pending, then updates with it',()=>{
  const finding=item(), row=(finding.ruleRun.params!.numeric_results as any[])[0];
  row.declaration={number:'2.77',unit:'×',metric:'加速比'};
  row.reason='实验结果证据1提到FP-Exp加速6.17倍。';
  row.evidence=[{candidate_id:'d1:t1',quote:'FP-Recip加速2.77倍。FP-Exp加速6.17倍。'}];
  finding.finding.message=row.reason;
  const anchor={anchor_id:'d1:t1',location:{page_number:53}} as any;
  setLocale('en');
  expect(numericHighlightTerms(finding,anchor)).toEqual(['2.77']);
  addTranslations({[row.reason]:'Evidence 1 reports FP-Exp speedup of 6.17 times.'});
  expect(numericHighlightTerms(finding,anchor)).toEqual(['6.17']);
});
it('uses measured glyph ranges instead of colouring the saved paragraph rectangle',()=>{
  const element=page('<span>均值3.57，后面是不相关的长段落。</span>');
  const source=annotation(),before=JSON.stringify(source);
  const result=refineNumericAnnotations(element,[source])[0];
  expect(result.rects).toHaveLength(1);
  expect(result.rects[0].x2-result.rects[0].x1).toBeLessThan(25);
  expect(result.rects[0].y2-result.rects[0].y1).toBeLessThan(15);
  expect(JSON.stringify(source)).toBe(before);
  element.remove();
});
it('does not match 5 inside 15, and does not keep a broad fallback rectangle',()=>{
  const element=page('<span>准确率15%</span>');
  expect(refineNumericAnnotations(element,[annotation(['5'])])[0].rects).toEqual([]);
  element.remove();
});
it('keeps spaces as numeric token boundaries within a native text node',()=>{
  const element=page('<span>AUC 0.9494；3.57 3.73</span>');
  expect(refineNumericAnnotations(element,[annotation(['0.9494','3.57','3.73'])])[0].rects).toHaveLength(3);
  element.remove();
});
it('ignores identical numbers outside the stored source region',()=>{
  const element=page('<span data-y="120">3.57</span><span data-y="700">3.57</span>');
  expect(refineNumericAnnotations(element,[annotation()])[0].rects).toHaveLength(1);
  element.remove();
});
it('leaves ambiguous repeated numbers unpainted instead of guessing a location',()=>{
  const element=page('<span>3.57</span><span data-y="180">3.57</span>');
  expect(refineNumericAnnotations(element,[annotation()])[0].rects).toEqual([]);
  element.remove();
});
it('keeps PDF coordinates correct after zoom',()=>{
  const normal=page('<span>3.57</span>');
  const zoomed=page('<span data-scale="2">3.57</span>',2);
  expect(refineNumericAnnotations(zoomed,[annotation()])[0].rects).toEqual(refineNumericAnnotations(normal,[annotation()])[0].rects);
  normal.remove();zoomed.remove();
});
it('does not paint broad source regions while the text layer is unavailable',()=>{
  const element=document.createElement('div');
  expect(refineNumericAnnotations(element,[annotation()])[0].rects).toEqual([]);
});
it('preserves other rules and their existing geometry',()=>{
  const other={...annotation(),ruleId:'sjtu_rule_24'};
  expect(refineNumericAnnotations(document.createElement('div'),[other])[0]).toBe(other);
});
it('shows only the selected numeric source in focus mode',()=>{
  render(<PdfOverlay pageNumber={4} pageWidth={595} pageHeight={842}
    annotations={[annotation(),{...annotation(),anchorId:'d1:t1'},{...annotation(),findingKey:'other',anchorId:'abstract-d2'}]}
    activeFindingKey="one" activeAnchorId="abstract-d1" density="focus" onFindingClick={()=>{}} onAnchorClick={()=>{}} />);
  expect(screen.getAllByRole('button')).toHaveLength(1);
});
