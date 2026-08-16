import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ExampleRuleCheckPage from '../src/pages/ExampleRuleCheckPage';
import { exampleDocumentPdf, generateExampleRule, listExampleDocuments } from '../src/api/exampleRuleCheck';
vi.mock('../src/api/exampleRuleCheck', () => ({
  listExampleDocuments: vi.fn(),
  exampleDocumentPdf: vi.fn(),
  uploadExampleDocument: vi.fn(),
  updateExampleAnnotations: vi.fn(),
  generateExampleRule: vi.fn(),
  trialExampleRule: vi.fn(),
  createExampleRule: vi.fn(),
}));
vi.mock('../src/components/paperLint/PdfPane', () => ({
  PdfPane: () => <div data-testid="example-annotation-pdf-pane" />,
}));
const renderPage = () =>
  render(
    <MemoryRouter>
      <ExampleRuleCheckPage />
    </MemoryRouter>,
  );
describe('example rule authoring UI', () => {
  beforeEach(() => {
    vi.mocked(listExampleDocuments).mockReset();
    vi.mocked(exampleDocumentPdf).mockReset();
    vi.mocked(exampleDocumentPdf).mockResolvedValue(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
    vi.mocked(generateExampleRule).mockReset();
  });
  it('explains the evidence-first empty state', async () => {
    vi.mocked(listExampleDocuments).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('还没有示例')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '生成规则草稿' })).toBeDisabled();
  });
  it('requires explicit consent and presents model failure clearly', async () => {
    vi.mocked(listExampleDocuments).mockResolvedValue([
      {
        id: 'doc-1',
        source_filename: '示例.pdf',
        annotations: [{ type: 'focus', page_number: 1, text_excerpt: '证据' }],
        created_at: '',
        updated_at: '',
      },
    ]);
    vi.mocked(generateExampleRule).mockRejectedValue(new Error('服务器尚未配置 DeepSeek'));
    renderPage();
    await screen.findByText('示例.pdf');
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/检查实验结果/), '检查结论');
    expect(screen.getByRole('button', { name: '生成规则草稿' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /允许本次外发/ }));
    await user.click(screen.getByRole('button', { name: '生成规则草稿' }));
    await waitFor(() => expect(screen.getByText('服务器尚未配置 DeepSeek')).toBeInTheDocument());
  });
});
