import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { NumericReviewDetails } from '../src/components/paperLint/NumericReviewDetails';

it('uses plain claim labels in the overview and prerequisite cards', () => {
  const { container } = render(<NumericReviewDetails run={{
    rule_id: 'abstract_numeric_consistency_check', rule_run_id: 'copy', severity: 'warning',
    execution_status: 'completed', outcome: 'passed', findings: [], params: {
      preconditions: ['abstract_numeric', 'contribution_mapping', 'experiment_subsection']
        .map(id => ({ id, passed: true })), numeric_results: [],
    },
  }} />);
  expect(screen.getByRole('heading', { name: '摘要论点核验' })).toBeInTheDocument();
  expect(screen.getByText('摘要中存在可核验的论点')).toBeInTheDocument();
  expect(screen.getByText('论点已映射到研究贡献')).toBeInTheDocument();
  expect(screen.getByText('论点已映射到实验子章节')).toBeInTheDocument();
  expect(container.textContent).not.toContain('数值型');
});
