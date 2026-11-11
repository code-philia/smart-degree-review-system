import { expect, it } from 'vitest';
import { flowWordSourceText } from '../src/utils/reportExport/wordSourceFlow';

it.each([
  ['中文原文，\n继续完整引用。', '中文原文，继续完整引用。'],
  ['A quoted\nEnglish sentence,\nwith every-word.\nOther.', 'A quoted English sentence, with every-word. Other.'],
  ['hyphen-\nated token', 'hyphen-ated token'],
  ['one\r\n  two\rthree', 'one two three'],
  ['研究\nLLM\n模型', '研究LLM模型'],
  [
    '段落一。\n\n段落二。\n（1）第一项\n内容续行。\n（2）第二项\n• Third item\ncontinued text',
    '段落一。\n\n段落二。\n（1）第一项内容续行。\n（2）第二项\n• Third item continued text',
  ],
  [
    'Intro.\n1. First item\n2. Second item\n- Third item\n  wrapped words',
    'Intro.\n1. First item\n2. Second item\n- Third item wrapped words',
  ],
  ['第一段\n \n\n第二段', '第一段\n\n\n第二段'],
  ['Intro.\n  - Nested item\n    wrapped words', 'Intro.\n  - Nested item wrapped words'],
  ['value\n0.5 remains unchanged', 'value 0.5 remains unchanged'],
  ['测试😀\n续文', '测试😀续文'],
])('reflows source display %j without losing non-whitespace characters', (source, expected) => {
  const result = flowWordSourceText(source);
  expect(result.text).toBe(expected);
  expect(result.text.replace(/\s/g, '')).toBe(source.replace(/\s/g, ''));
  expect(result.offsets).toHaveLength(source.length + 1);
  expect(result.offsets[0]).toBe(0);
  expect(result.offsets.at(-1)).toBe(result.text.length);
});

it('maps marks after removed PDF linebreaks, including CRLF, to the same source characters', () => {
  const source = '原文\r\n错字片段 and\nmarked text';
  const result = flowWordSourceText(source);
  for (const value of ['错字片段', 'marked text']) {
    const start = source.indexOf(value),
      end = start + value.length;
    expect(result.text.slice(result.offsets[start], result.offsets[end])).toBe(value);
  }
});

it('keeps a source mark spanning a removed break on the same visible characters', () => {
  const source = '前文疑似\n错字后文',
    start = source.indexOf('疑似'),
    end = source.indexOf('后文');
  const result = flowWordSourceText(source);
  expect(result.text.slice(result.offsets[start], result.offsets[end])).toBe('疑似错字');
});
