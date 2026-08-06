import { describe, expect, it } from 'vitest';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
import { findingAnnotations, findingTarget, groupAnnotationsByPage } from '../src/components/paperLint/geometry';

function item(): PaperLintFindingItem {
  return {
    key: 'finding-1',
    index: 0,
    ruleRun: {
      rule_run_id: 'run-1',
      rule_id: 'toc_format_check',
      severity: 'warning',
      execution_status: 'completed',
      evidence_mode: 'derived',
      outcome: 'issues_found',
      findings: [],
    },
    finding: {
      finding_id: 'finding-1',
      rule_id: 'toc_format_check',
      message: '目录条目缩进不一致。',
      location: {
        type: 'pdf_bbox',
        page_number: 3,
        bounding_rect: { x1: 20, y1: 100, x2: 180, y2: 120, width: 595, height: 842, page_number: 3 },
        rects: [],
        text_excerpt: '1.1 研究背景',
      },
      anchors: [
        {
          anchor_id: 'anchor-1',
          role: 'evidence',
          label: '相邻条目',
          location: {
            type: 'pdf_bbox',
            page_number: 3,
            bounding_rect: { x1: 40, y1: 125, x2: 200, y2: 145, width: 595, height: 842, page_number: 3 },
            rects: [{ x1: 40, y1: 125, x2: 200, y2: 145, width: 595, height: 842, page_number: 3 }],
          },
        },
      ],
    },
  };
}

describe('paper-lint PDF geometry', () => {
  it('uses the bounding box when review-pilot returns no detailed rect list', () => {
    const annotations = findingAnnotations(item());
    expect(annotations).toHaveLength(2);
    expect(annotations[0]).toMatchObject({ findingKey: 'finding-1', pageNumber: 3, textExcerpt: '1.1 研究背景' });
    expect(annotations[0].rects).toHaveLength(1);
    expect(groupAnnotationsByPage(annotations).get(3)).toHaveLength(2);
  });

  it('targets a selected evidence anchor before the finding location', () => {
    const target = findingTarget(item(), 'anchor-1');
    expect(target.type).toBe('bbox');
    if (target.type === 'bbox') {
      expect(target.annotation).toMatchObject({ anchorId: 'anchor-1', pageNumber: 3 });
      expect(target.annotation.boundingRect.y1).toBe(125);
    }
  });
});
