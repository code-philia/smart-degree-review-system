import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import App from '../src/App';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'student01', username: 'student01', role: 'STUDENT' }, logout: async () => {} }),
}));
vi.mock('../src/pages/NormativeCheckPage', () => ({ default: ({ mode }: { mode: string }) => <h1>{mode === 'semantic' ? '摘要核验内容' : '上传内容'}</h1> }));
vi.mock('../src/pages/NormativeReportPage', () => ({ default: () => <h1>历史内容</h1> }));
vi.mock('../src/pages/PaperLintReportPage', () => ({ default: () => <h1>报告内容</h1> }));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="当前地址">{location.pathname}{location.search}{location.hash}</output>;
}
it.each([
  ['/paper-upload', '/paper-upload', '上传内容', '论文上传'],
  ['/abstract-check', '/abstract-check', '摘要核验内容', '摘要数值语义检测'],
  ['/reports', '/reports', '历史内容', '历史报告'],
  ['/reports/pdf/saved?view=pdf#page=3', '/reports/pdf/saved?view=pdf#page=3', '报告内容', '历史报告'],
  ['/', '/paper-upload', '上传内容', '论文上传'],
  ['/thirty-rules-check?source=bookmark#rules', '/paper-upload?source=bookmark#rules', '上传内容', '论文上传'],
  ['/semantic-rules-check', '/abstract-check', '摘要核验内容', '摘要数值语义检测'],
  ['/thirty-rules-check/reports', '/reports', '历史内容', '历史报告'],
  ['/thirty-rules-check/reports/pdf/saved?view=pdf#page=3', '/reports/pdf/saved?view=pdf#page=3', '报告内容', '历史报告'],
])('opens %s at its meaningful canonical URL', async (entry, target, heading, active) => {
  render(<MemoryRouter initialEntries={[entry]}><App /><LocationProbe /></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
  expect(screen.getByLabelText('当前地址')).toHaveTextContent(target);
  const sidebar = screen.getByLabelText('主导航菜单');
  for (const [name, path] of [['论文上传', '/paper-upload'], ['摘要数值语义检测', '/abstract-check'], ['历史报告', '/reports']]) {
    const link = within(sidebar).getByRole('link', { name, exact: true });
    expect(link).toHaveAttribute('href', path);
    if (name === active) expect(link).toHaveAttribute('aria-current', 'page');
    else expect(link).not.toHaveAttribute('aria-current');
  }
});
