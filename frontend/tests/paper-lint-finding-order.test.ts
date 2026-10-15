import { describe, expect, it } from 'vitest';
import type { PaperLintResult } from '../src/api/paperLint';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
function report(entries: Array<[number | string, Array<[string, number, number?]>]>): PaperLintResult {
  return {
    rule_runs: entries.map(([number, findings]) => {
      const rule_id = typeof number === 'number' ? 'sjtu_rule_' + number : number;
      return {
        rule_id,
        findings: findings.map(([id, page, y = 10]) => ({
          finding_id: id,
          rule_id,
          message: id,
          location: {
            type: 'pdf_bbox',
            page_number: page,
            bounding_rect: { x1: 1, y1: y, x2: 50, y2: y + 5, width: 100, height: 200, page_number: page },
            rects: [],
          },
        })),
      };
    }),
  } as PaperLintResult;
}
describe('PDF finding order', () => {
  it('puts lower rule numbers first even on later PDF pages', () => {
    const input = report([
      [15, [['f15', 1]]],
      [11, [['f11', 99]]],
      [2, [['f2', 30]]],
    ]);
    const items = flattenPaperLintFindings(input);
    expect(items.map((item) => item.key)).toEqual(['f2', 'f11', 'f15']);
    expect(items.map((item) => item.index)).toEqual([0, 1, 2]);
    expect(input.rule_runs.map((run) => run.rule_id)).toEqual(['sjtu_rule_15', 'sjtu_rule_11', 'sjtu_rule_2']);
  });
  it('keeps page and vertical position order within each rule', () => {
    const input = report([
      [
        11,
        [
          ['later-page', 3],
          ['lower', 2, 60],
          ['upper', 2, 10],
          ['same-position', 2, 10],
        ],
      ],
    ]);
    expect(flattenPaperLintFindings(input).map((item) => item.key)).toEqual([
      'upper',
      'same-position',
      'lower',
      'later-page',
    ]);
  });
  it('keeps nonnumbered checks in page order after numbered rules', () => {
    const input = report([
      ['semantic_b', [['semantic-later', 3]]],
      [11, [['f11', 99]]],
      ['semantic_a', [['semantic-earlier', 2]]],
    ]);
    expect(flattenPaperLintFindings(input).map((item) => item.key)).toEqual([
      'f11',
      'semantic-earlier',
      'semantic-later',
    ]);
  });
});
