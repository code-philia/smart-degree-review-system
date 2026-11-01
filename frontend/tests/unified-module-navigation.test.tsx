import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import ModuleTabs from '../src/components/ui/ModuleTabs';
import { findNavItemLabel, getVisibleNavGroups } from '../src/nav/navigationConfig';

describe('FEAT-UNIFIED-MODULE-HISTORY unified module navigation', () => {
  it('keeps one upload workflow and history in the sidebar', () => {
    const visibleLabels = getVisibleNavGroups('STUDENT').flatMap((group) => group.items.map((item) => item.label));

    expect(visibleLabels).toEqual(['论文上传', '历史报告']);
    expect(findNavItemLabel('/paper-upload')).toEqual({ groupTitle: '论文规范性检测', label: '论文上传' });
    expect(findNavItemLabel('/reports')).toEqual({
      groupTitle: '论文规范性检测',
      label: '历史报告',
    });
    expect(findNavItemLabel('/duplication-history')).toBeNull();
    expect(findNavItemLabel('/abstract-check')).toEqual({
      groupTitle: '论文规范性检测', label: '论文上传',
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
