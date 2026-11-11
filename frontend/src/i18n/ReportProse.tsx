import { useSyncExternalStore } from 'react';
import { getLocale, getPresentationRevision, getTranslation, subscribe, translate } from './locale';
import { preserveText } from './jsx-runtime';

const han = /\p{Script=Han}/u;
const quotations = /“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|《[^》]*》|〈[^〉]*〉|"[^"\n]*"|'[^'\n]*'/g;
function sourceLiteralsFor(text: string, sources: readonly string[]) {
  const literals = [...text.matchAll(quotations)].map(match => match[0]);
  const typo = /^(?:疑似错别字|疑似错字)[：:][ \t]*([\s\S]+)$/.exec(text);
  if (typo) literals.push(typo[1]);
  literals.push(...sources.filter(source => source && text.includes(source)));
  return [...new Set(literals.filter(literal => han.test(literal)))].sort((a,b) => b.length-a.length);
}
function completeEnglish(value: string, sources: readonly string[]) {
  let prose = value;
  for (const literal of sources) prose = prose.split(literal).join('');
  return !han.test(prose) && (!han.test(value) || /[A-Za-z]/.test(prose));
}

// Verify translated prose rather than treating every mapping as completed English.
// Only proven original quotations/targets may retain their original language.
export function ReportProse({ text, sourceLiterals = [] }: { text?: string | null; sourceLiterals?: readonly string[] }) {
  useSyncExternalStore(subscribe, getPresentationRevision, getPresentationRevision);
  if (!text) return null;
  if (getLocale() !== 'en') return preserveText(text);
  const sources = sourceLiteralsFor(text, sourceLiterals);
  const approved = translate(text);
  if (completeEnglish(approved, sources)) return preserveText(approved);
  const mapped = getTranslation(text);
  if (typeof mapped === 'string' && completeEnglish(mapped, sources)) return preserveText(mapped);
  return <span>English translation is not ready yet.</span>;
}
