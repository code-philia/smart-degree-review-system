import type { PaperLintFindingAnchor, PdfRect } from '../../api/paperLint';
import type { PaperLintFindingItem } from './model';
import type { PaperLintPdfAnnotation } from './geometry';
import { assessmentClaim, claimSummary, compositeClaim, evidencePresentation, object, objects, text } from './numericFindingPresentation';
import { resolveReportProseText } from '../../i18n/ReportProse';
import { getLocale } from '../../i18n/locale';

const RULE='abstract_numeric_consistency_check';
const scalar=/(?<![A-Za-z\d.])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?[%％]?/g;
const canonical=(value:string)=>value.normalize('NFKC').replace(/[%％]$/,'').replace(/−/g,'-');

function numbers(value:string) {
  const clean=value.normalize('NFKC')
    .replace(/\b[a-z]+\d+:[a-z]+\d+\b/gi,' ')
    .replace(/第\s*\d+\s*页/g,' ')
    .replace(/(?:图|表|公式|Table|Fig\.?|Eq\.?)\s*\d+(?:[-.]\d+)*/gi,' ');
  return [...clean.matchAll(scalar)].map(match=>{
    const raw=canonical(match[0]);
    return /^-/.test(raw) && match.index!>0 && /\d/.test(clean[match.index!-1]) ? raw.slice(1) : raw;
  });
}

export function numericHighlightTerms(item:PaperLintFindingItem,anchor?:PaperLintFindingAnchor) {
  if(item.ruleRun.rule_id!==RULE) return undefined;
  const rows=objects(item.ruleRun.params?.numeric_results);
  const row=rows.find(candidate=>item.finding.finding_id===`${RULE}_${text(candidate.declaration_id)}`);
  if(!row) return [];
  const reason=text(row.reason), declaration=object(row.declaration);
  const sourceLiterals=[item.finding.location?.text_excerpt,
    ...(item.finding.anchors||[]).map(anchor=>anchor.location?.text_excerpt),
    ...(item.finding.evidence||[]).map(evidence=>evidence.quote),
  ].filter((value):value is string=>typeof value==='string'&&Boolean(value.trim()));
  let analysis=resolveReportProseText({text:item.finding.message || reason,sourceLiterals});
  const composite=compositeClaim(rows,row);
  const abstract=!anchor || anchor.anchor_id.startsWith('abstract-') || /摘要|abstract/i.test(anchor.label||'');
  let relevant='';
  if(abstract) {
    const abstractAnchor=item.finding.anchors?.find(anchor=>anchor.anchor_id.startsWith('abstract-')||/摘要/.test(anchor.label||''));
    const original=text(declaration.text)||text(abstractAnchor?.location.text_excerpt)
      ||text(item.finding.evidence?.find(entry=>entry.id?.startsWith('abstract-'))?.quote);
    const unit=text(declaration.unit), number=text(declaration.number), metric=text(declaration.metric);
    const value=number ? `${number}${unit ? unit==='%' ? unit : ` ${unit}` : ''}` : '';
    const point=assessmentClaim(getLocale()==='en' ? analysis : reason)||claimSummary(original,metric,value);
    relevant=composite ? composite.values.flat().join(' ') : `${point||`${metric} ${value}`} ${text(declaration.condition)}`;
  } else {
    const evidence=objects(row.evidence).filter(entry=>text(entry.quote));
    const index=evidence.findIndex(entry=>text(entry.candidate_id || entry.id)===anchor.anchor_id);
    if(index<0) return [];
    evidence.forEach((entry,index)=>{
      const id=text(entry.candidate_id || entry.id);
      if(id) analysis=analysis.split(id).join(`实验结果证据${index+1}`);
    });
    relevant=evidencePresentation(text(evidence[index].quote),text(declaration.metric),text(declaration.method),reason,
      Boolean(composite),analysis,index).focusText;
  }
  return [...new Set(numbers(relevant))].filter(value=>value.length<=30);
}

export function annotationIsActive(annotation:PaperLintPdfAnnotation,findingKey:string|null,anchorId:string|null) {
  if(annotation.findingKey!==findingKey) return false;
  if(anchorId) return annotation.anchorId===anchorId;
  if(annotation.ruleId!==RULE) return true;
  return !annotation.anchorId || annotation.anchorId.startsWith('abstract-') || /摘要|abstract/i.test(annotation.anchorLabel||'');
}

type Hit={value:string;rects:DOMRect[]};
function textHits(page:HTMLElement,wanted:Set<string>):Hit[] {
  const layer=page.querySelector('.textLayer');
  if(!layer || !wanted.size) return [];
  const walker=page.ownerDocument.createTreeWalker(layer,4);
  const hits:Hit[]=[];
  let node:Node|null;
  while((node=walker.nextNode())) {
    const source=node.textContent||'';
    let normalized='';
    const offsets:number[]=[];
    for(let i=0;i<source.length;i++) {
      for(const character of source[i].normalize('NFKC')) {
        normalized+=character; offsets.push(i);
      }
    }
    for(const match of normalized.matchAll(scalar)) {
      let value=canonical(match[0]);
      if(value.startsWith('-') && match.index!>0 && /\d/.test(normalized[match.index!-1])) value=value.slice(1);
      if(!wanted.has(value)) continue;
      const range=page.ownerDocument.createRange();
      try {
        range.setStart(node,offsets[match.index!]);
        range.setEnd(node,offsets[match.index!+match[0].length-1]+1);
        const rects=typeof range.getClientRects==='function' ? Array.from(range.getClientRects()).filter(rect=>rect.width>0&&rect.height>0) : [];
        if(rects.length) hits.push({value,rects});
      } catch { /* A replaced text layer has no verified glyph location yet. */ }
      finally {range.detach();}
    }
  }
  return hits;
}

export function refineNumericAnnotations(page:HTMLElement,annotations:PaperLintPdfAnnotation[]) {
  const wanted=new Set(annotations.filter(a=>a.ruleId===RULE).flatMap(a=>a.focusTerms||[]));
  const hits=textHits(page,wanted);
  const pageRect=page.getBoundingClientRect();
  return annotations.map(annotation=>{
    if(annotation.ruleId!==RULE) return annotation;
    const rects:PdfRect[]=[];
    if(pageRect.width>0 && pageRect.height>0) {
      const width=annotation.boundingRect.width,height=annotation.boundingRect.height;
      for(const value of annotation.focusTerms||[]) {
        const matches=hits.filter(hit=>hit.value===value).flatMap(hit=>{
          const converted=hit.rects.map(rect=>({
            x1:(rect.left-pageRect.left)*width/pageRect.width,
            y1:(rect.top-pageRect.top)*height/pageRect.height,
            x2:(rect.right-pageRect.left)*width/pageRect.width,
            y2:(rect.bottom-pageRect.top)*height/pageRect.height,
            width,height,page_number:annotation.pageNumber,
          }));
          return converted.every(rect=>annotation.rects.some(source=>{
            const x=(rect.x1+rect.x2)/2,y=(rect.y1+rect.y2)/2;
            return x>=source.x1-2&&x<=source.x2+2&&y>=source.y1-2&&y<=source.y2+2;
          })) ? [converted] : [];
        });
        // A repeated value without a unique source position is not a reliable match.
        if(matches.length===1) rects.push(...matches[0]);
      }
    }
    const unique=[...new Map(rects.map(rect=>[`${rect.x1}:${rect.y1}:${rect.x2}:${rect.y2}`,rect])).values()];
    const boundingRect=unique.length ? {...annotation.boundingRect,
      x1:Math.min(...unique.map(r=>r.x1)),y1:Math.min(...unique.map(r=>r.y1)),
      x2:Math.max(...unique.map(r=>r.x2)),y2:Math.max(...unique.map(r=>r.y2)),
    } : annotation.boundingRect;
    return {...annotation,rects:unique,boundingRect};
  });
}
