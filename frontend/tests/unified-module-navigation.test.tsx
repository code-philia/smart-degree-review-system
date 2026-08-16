import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import ModuleTabs from '../src/components/ui/ModuleTabs';
import { findNavItemLabel, getVisibleNavGroups } from '../src/nav/navigationConfig';

describe('FEAT-UNIFIED-MODULE-HISTORY unified module navigation', () => {
  it('keeps one sidebar entry per business module and maps legacy history paths back to it', () => {
    const visibleLabels = getVisibleNavGroups('STUDENT').flatMap((group) => group.items.map((item) => item.label));

    expect(visibleLabels).toContain('基础规则检测');
    expect(visibleLabels).toContain('高级语义规则检测');
    expect(visibleLabels).not.toContain('论文相似度检测');
    expect(visibleLabels).toContain('论文润色');
    expect(visibleLabels).toContain('创新性量表评估');
    expect(visibleLabels).toContain('规则化辅助评阅');
    expect(visibleLabels).not.toContain('规范报告历史');
    expect(visibleLabels).not.toContain('相似度检测历史');
    expect(visibleLabels).not.toContain('润色历史');
    expect(visibleLabels).not.toContain('创新评估历史');
    expect(visibleLabels).not.toContain('辅助评阅历史');

    expect(findNavItemLabel('/advanced-semantic-rule-check/novelty-detection')).toEqual({
      groupTitle: '检测与生成',
      label: '高级语义规则检测',
    });
    expect(findNavItemLabel('/duplication-history')).toBeNull();
    expect(findNavItemLabel('/polish-history/whole/result-001')).toEqual({
      groupTitle: '检测与生成',
      label: '论文润色',
    });
    expect(findNavItemLabel('/innovation-assessments/report-001')).toEqual({
      groupTitle: '评估与评阅',
      label: '创新性量表评估',
    });
  });

  it('renders accessible in-page tabs with the current tab and history count', () => {
    render(
      <MemoryRouter>
        <ModuleTabs
          ariaLabel="论文相似度检测功能导航"
          items={[
            { label: '发起检测', to: '/duplication-detect', active: false },
            { label: '历史记录', to: '/duplication-history', active: true, count: 2 },
          ]}
        />
      </MemoryRouter>,
    );

    const navigation = screen.getByRole('navigation', { name: '论文相似度检测功能导航' });
    expect(navigation).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '发起检测' })).toHaveAttribute('href', '/duplication-detect');
    expect(screen.getByRole('link', { name: '历史记录2' })).toHaveAttribute('aria-current', 'page');
  });
});
