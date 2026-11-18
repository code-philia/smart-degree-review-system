const reference = /\b(?:d\d+\s*:\s*)?[et]\d+\b|实验结果证据\s*\d+|\b(?:evidence|candidate)\s*#?\s*\d+\b/giu;
const prefix = /^(?:(?:检查了?|其中|其他|非)?(?:主证据|候选证据|候选论据|证据|论据)|(?:the\s+)?(?:(?:primary|main|other|candidate|experimental)\s+)*(?:evidence|candidates?))[\s:：()（）-]*$/i;
const continuation = /^(?:但|不过|然而|且|并且|该(?:证据|段落|表格|结果)|其中|这(?:一|些)(?:证据|表格|结果)|However\b|But\b|Yet\b|This\b|These\b|It\b)/i;
const conclusion = /^(?:所有|因此|故|综上|综合|由于|Therefore\b|Overall\b|In conclusion\b)/i;

function description(sentence: string) {
  let value = sentence.replace(reference, '')
    .replace(/第\s*\d+(?:\s*[、,]\s*\d+)*\s*页/g, '')
    .replace(/\b(?:pages?\s+|p\.?\s*)\d+(?:\s*[,–-]\s*\d+)*/gi, '')
    .replace(/^(?:检查了?|其中|其他|非)?(?:主证据|候选证据|候选论据|证据|论据)\s*[：:]?\s*/u, '')
    .replace(/^(?:the\s+)?(?:(?:primary|main|other|candidate|experimental)\s+)*(?:evidence|candidates?)\s*[:：]?\s*/i, '')
    .replace(/[（(]\s*[）)]/g, '');
  let previous: string;
  do {
    previous = value;
    value = value.replace(/^[\s、,，:：;；-]+/u, '').replace(/^(?:和|及|与|以及|等|and\b|or\b)\s*/i, '');
  } while (value !== previous);
  return value.replace(/^(?:为|描述|提到|提及|显示|指出|表明|说明)\s*/u, '')
    .replace(/^(?:describes?|reports?|mentions?|shows?|is|are)\s+/i, '')
    .replace(/[ \t]{2,}/g, ' ').trim();
}

// Split at a new candidate only after a description, outside parentheses.
// A list of IDs sharing one description stays together.
function candidateGroups(sentence: string) {
  const references = [...sentence.matchAll(reference)];
  const groups: string[] = [];
  let start = 0;
  for (const match of references.slice(1)) {
    const before = sentence.slice(start, match.index);
    const boundary = before.match(/[；;、]\s*$/u);
    if (!boundary) continue;
    let depth = 0;
    for (const char of before) {
      if (char === '(' || char === '（') depth++;
      if (char === ')' || char === '）') depth--;
    }
    if (depth !== 0 || !description(before).replace(/[。；;、]/g, '').trim()) continue;
    groups.push(before);
    start = match.index!;
  }
  groups.push(sentence.slice(start));
  return groups;
}

/** Extract saved descriptions only; never create evidence, locations or verdicts. */
export function analysisEvidenceDescriptions(analysis: string): string[] {
  const source = analysis.replace(/^(?:论据不明确|论点与论据不一致)[：:]\s*/u, '');
  const sentences = source.split(/(?<=[。！？])\s*|(?<=[.!?])\s+(?=[A-Z])/u).filter(Boolean);
  const result: string[] = [];
  let active = -1;
  for (const sentence of sentences) {
    if (conclusion.test(sentence)) { active = -1; continue; }
    const first = [...sentence.matchAll(reference)][0];
    const lead = first ? sentence.slice(0, first.index).trim() : '';
    if (first && (!lead || prefix.test(lead))) {
      for (const group of candidateGroups(sentence)) {
        const value = description(group);
        active = value ? result.push(value) - 1 : -1;
      }
    } else if (active >= 0 && continuation.test(sentence)) {
      result[active] += ` ${description(sentence)}`;
    } else {
      active = -1;
    }
  }
  return [...new Set(result)];
}
