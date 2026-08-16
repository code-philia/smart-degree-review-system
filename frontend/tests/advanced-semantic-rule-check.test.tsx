import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import AdvancedSemanticRuleCheckPage from '../src/pages/AdvancedSemanticRuleCheckPage';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'anonymous', user: null }),
}));

function renderPage(path = '/advanced-semantic-rule-check') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/advanced-semantic-rule-check" element={<AdvancedSemanticRuleCheckPage />} />
        <Route path="/advanced-semantic-rule-check/:example" element={<AdvancedSemanticRuleCheckPage />} />
        <Route path="/review-cases/:caseId" element={<div>内置案例</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('advanced semantic rule check examples', () => {
  it('defaults to the fixed claim-evidence inconsistency example', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: '高级语义规则检测' })).toBeInTheDocument();
    expect(screen.getByText('请先登录后查看案例')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
  });

  it('renders the novelty example at its fixed URL', () => {
    renderPage('/advanced-semantic-rule-check/novelty-detection');
    expect(screen.getByText('不新颖')).toBeInTheDocument();
    expect(screen.getByText('0.20')).toBeInTheDocument();
    expect(screen.getByText('0 很不新颖')).toBeInTheDocument();
    expect(screen.getByText('Factored Adaptation for Non-Stationary Reinforcement Learning')).toBeInTheDocument();
  });

  it('renders the baseline recommendation example at its fixed URL', () => {
    renderPage('/advanced-semantic-rule-check/baseline-recommendation');
    expect(screen.getByText('优先对比工作')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'GPT4MTS: Prompt-based Large Language Model for Multimodal Time-series Forecasting',
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('两篇文章解决同一个问题，且方法高度相似，建议作为优先对比工作。')).toHaveLength(2);
  });
});
