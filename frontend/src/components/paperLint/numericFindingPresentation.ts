export type Row = Record<string, unknown>;
export function objects(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((v): v is Row => Boolean(v && typeof v === 'object' && !Array.isArray(v))) : [];
}
export function text(value: unknown) { return typeof value === 'string' ? value.trim() : typeof value === 'number' && Number.isFinite(value) ? String(value) : ''; }
export function object(value: unknown): Row { return value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {}; }
export function proseText(value: string) { return value.replace(/([\p{Script=Han}])[ \t]*\r?\n[ \t]*(?=\p{Script=Han})/gu, '$1'); }


export function evidenceSummary(analysis: string, index: number, quote: string, metric: string) {
  const label=new RegExp(`(?:实验结果证据|Evidence\\s*)${index+1}(?!\\d)`, 'i');
  const sentences=analysis.split(/(?<=[。！？])|(?<=[.!?])\s+(?=[A-Z])/u);
  const sentence=sentences.find(sentence=>label.test(sentence));
  if(sentence){
    const match=label.exec(sentence)!;
    let body=sentence.slice(match.index+match[0].length).replace(/^[\s（）()]+/,'').replace(/^(?:中|提到|显示|表明|指出)[：:]?\s*/,'');
    // Preserve the entire cited sentence, including applicability and attribution.
    body=body.trim();
    if(body && !/实验结果证据|Evidence\s*\d/i.test(body)) return body.replace(/[。；;]$/,'')+'。';
  }
  const flow=proseText(quote).replace(/\s+/g,' ').trim();
  const words=metric.match(/[A-Za-z][A-Za-z0-9@._+-]*/)?.[0] || metric;
  const parts=flow.split(/(?<=[。；;])/).filter(part=>!/^(?:和|及|以及)\s*[-+]?\d/.test(part.trim()));
  const selected=parts.find(part=>words && part.includes(words) && /\d/.test(part));
  if(selected && selected.length<=240) return selected.trim();
  const first=parts.find(part=>part.length<=180 && /\d/.test(part));
  return first?.trim() || (flow.length<=180 ? flow : '请查看该论据原文中的具体实验结果。');
}


export function compositeClaim(rows: Row[], row: Row | undefined) {
  if (!row || !/声明整体/.test(text(row.reason))) return null;
  const declaration=object(row.declaration), statement=text(declaration.text).replace(/\s/g,'');
  if (!statement || !text(declaration.metric) || !text(declaration.unit)) return null;
  const members=rows.map(entry=>object(entry.declaration)).filter(entry=>
    text(entry.text).replace(/\s/g,'')===statement && text(entry.metric)===text(declaration.metric)
    && text(entry.unit)===text(declaration.unit) && text(entry.method) && text(entry.condition) && text(entry.number));
  const methods=[...new Set(members.map(entry=>text(entry.method)))];
  const scopeOf=(entry:Row)=>text(entry.condition).replace(text(entry.method),'').replace(/^[，,、；;\s]+|[，,、；;\s]+$/g,'');
  const scopes=[...new Set(members.map(scopeOf))];
  if(methods.length<2 || scopes.length<2 || methods.length>4 || scopes.length>4
    || scopes.some(scope=>!scope) || members.length!==methods.length*scopes.length) return null;
  const cells=methods.map(method=>scopes.map(scope=>members.filter(entry=>text(entry.method)===method&&scopeOf(entry)===scope)));
  if(cells.some(cells=>cells.some(cell=>cell.length!==1))) return null;
  return { metric:text(declaration.metric), unit:text(declaration.unit), methods, scopes,
    values:cells.map(cells=>cells.map(cell=>text(cell[0].number))) };
}


export function readableTable(quote: string) {
  const lines = quote.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const first = lines.findIndex(line => line.includes('|'));
  if (first < 0) return null;
  const table = lines.slice(first);
  if (table.length < 2 || table.some(line => !line.includes('|'))) return null;
  const rows = table.map(line => line.split('|').map(cell => cell.trim()));
  const width = rows[0].length;
  if (width < 2 || rows.some(row => row.length !== width || row.filter(Boolean).length < width - 1)) return null;
  if (rows.some(row => row.some(cell => cell.length > 70 || (cell.match(/-?\d+(?:\.\d+)?/g) || []).length > 2))) return null;
  return { caption: lines.slice(0, first).join('\n'), rows };
}


export function sourceValues(quote: string, metric: string, reason: string) {
  // Combined metrics, ranges and hypothetical statements have no safe scalar summary.
  const label = metric.match(/^([A-Za-z][A-Za-z0-9@._+-]*)(?:相对提升|提升|得分|分数|准确率)?$/)?.[1];
  if (!label) return null;
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const scalar = '[-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?[%％]?';
  const pattern = new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])\\s*(?:从|由)\\s*(${scalar})\\s*(?:提升至|增长至|提高至|降低至|下降至|增加至|升至|降至|提高到|增加到|到|至)\\s*(${scalar})(?![\\dA-Za-z%％]|[,.，]\\d|[–—~～-]\\s*\\d)(?=\\s*(?:[，,。；;]|这组数值|$))`, 'g');
  const pairs = [...quote.matchAll(pattern)];
  const associations = [...reason.matchAll(pattern)];
  const associated = pairs.filter(pair => associations.some(other => other[1] === pair[1] && other[2] === pair[2]));
  const match = associated.length === 1 ? associated[0] : undefined;
  if (!match || match.index === undefined) return null;
  const start = quote.lastIndexOf('。', match.index) + 1;
  const end = quote.indexOf('。', match.index + match[0].length);
  const context = quote.slice(start, end < 0 ? quote.length : end + 1).trim();
  const linked = associations.find(pair => pair[1] === match[1] && pair[2] === match[2]);
  const reasonSentence = reason.split(/(?<=[。！？；;])/).find(sentence => linked && sentence.includes(linked[0])) || '';
  if (/若|如果|假设|假定|未|没有|不支持|不成立|可能|计划|预计|预期|目标|希望|拟将|有望|尚不能|\b(?:if|hypothetical|not|no evidence)\b/i.test(context + reasonSentence)) return null;
  return { label, before: match[1], after: match[2], context };
}


export function tableFocus(table: NonNullable<ReturnType<typeof readableTable>>, metric: string, method: string) {
  if (!metric || !method) return null;
  const normalize = (v: string) => v.replace(/\s/g, '');
  const columns = table.rows[0].map((cell, i) => ({ cell, i })).filter(({ cell }) => normalize(cell).replace(/[（(][^（）()]+[）)]$/, '') === normalize(metric));
  const rows = table.rows.slice(1).filter(row => normalize(row[0]) === normalize(method));
  if (columns.length !== 1 || rows.length !== 1) return null;
  const cell = rows[0][columns[0].i];
  if (!/^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?[%％]?$/.test(cell)) return null;
  const unit = columns[0].cell.match(/[（(]([^）)]+)[）)]$/)?.[1] || '';
  return { method: rows[0][0], value: `${cell}${unit && !cell.endsWith(unit) ? ` ${unit}` : ''}` };
}

export function tableMetricColumn(table: NonNullable<ReturnType<typeof readableTable>>, metric: string) {
  const columns=table.rows[0].map((cell,i)=>({cell,i})).filter(({cell})=>cell.replace(/\s/g,'').replace(/[（(][^（）()]+[）)]$/,'')===metric.replace(/\s/g,''));
  if(columns.length!==1 || columns[0].i===0) return null;
  return {caption:table.caption,rows:table.rows.map((cells,i)=>[cells[0] || (i===0?'方法':''),cells[columns[0].i]])};
}

/** Shared by the card and PDF highlighting, so both describe the same evidence. */
export function evidencePresentation(quote: string, metric: string, method: string, reason: string,
  composite: boolean, analysis: string, index: number) {
  const table = readableTable(quote);
  const largeTable = table && (table.rows.length > 6 || table.rows[0].length > 6);
  const unclear = !table && ((quote.match(/\|/g) || []).length >= 6 || quote.split('\n').filter(line => line.includes('|')).length >= 2);
  const values = !table && !unclear ? sourceValues(quote, metric, reason) : null;
  const focusedTable = composite && table ? tableMetricColumn(table, metric) : null;
  const cell = table ? tableFocus(table, metric, method) : null;
  const visibleQuote = evidenceSummary(analysis, index, values?.context || quote, metric);
  // A negative comparison is an explanation, not a value found in this source.
  const factualText = visibleQuote.split(/(?:也?未|但未|并非|而非|没有|无法|不能|\b(?:not|no evidence|rather than)\b)/i)[0];
  const focusText = focusedTable ? focusedTable.rows.slice(1).map(row => row[1]).join(' ')
    : values ? `${values.before} ${values.after}` : cell ? cell.value : unclear || largeTable ? ''
    : table ? table.rows.slice(1).flatMap(row => row.slice(1)).join(' ') : factualText;
  return { table, largeTable, unclear, values, focusedTable, cell, visibleQuote, focusText };
}


export function claimSummary(source: string, metric: string, value: string) {
  if (!source) return '';
  const flow = proseText(source).replace(/\s+/g, ' ').trim();
  const clauses: string[] = [];
  let start=0, depth=0;
  for (let i=0;i<flow.length;i++) {
    if ('（([{【'.includes(flow[i])) depth++;
    else if ('）)]}】'.includes(flow[i])) depth=Math.max(0,depth-1);
    if (depth===0 && /[，；;。！？!?]/.test(flow[i])) {
      const clause=flow.slice(start,i+1).trim();
      if(clause) clauses.push(clause);
      start=i+1;
    }
  }
  if(start<flow.length) clauses.push(flow.slice(start));
  const normalize=(v:string)=>v.replace(/\s/g,'').replace(/[–—−]/g,'-');
  const needle=normalize(value).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const token=needle ? new RegExp(`(?<![\\d.])${needle}(?![\\d.])`) : null;
  const candidates=[...new Set(clauses.filter(clause=>token?.test(normalize(clause))))];
  const withMetric=candidates.filter(clause=>normalize(clause).includes(normalize(metric)));
  const selected=withMetric.length===1 ? withMetric[0] : candidates.length===1 ? candidates[0] : '';
  // Complete clauses preserve bounds, baseline/result pairs and bracketed context.
  // Ambiguous source statements stay intact rather than inventing a paraphrase.
  return selected ? selected.replace(/[，；;]$/, '。') : metric && value ? `${metric}：${value}` : flow;
}

export function assessmentClaim(analysis: string) {
  const first=analysis.replace(/^(?:论点与论据不一致|论据不明确)[：:]\s*/,'').split(/(?<=[。！？])|(?<=[.!?])\s+(?=[A-Z])/u)[0] || '';
  const match=/^声明(?:称|指出|声称|表示)[：:]?\s*([\s\S]+)$/.exec(first)
    || /^(?:The\s+)?(?:claim|abstract|statement|declaration)\s+(?:states|claims|reports|says|asserts)(?:\s+that)?[：:]?\s+([\s\S]+)$/i.exec(first);
  return match?.[1] || '';
}
