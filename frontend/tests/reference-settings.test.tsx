import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock('../src/api', () => ({ default: api }));
import { ReferenceSettings } from '../src/components/ReferenceSettings';
import { setLocale } from '../src/i18n/locale';

beforeEach(() => {
  setLocale('zh');
  api.get.mockReset().mockResolvedValue({ data: { configured: false, key_hint: null, storage_available: true } });
  api.put.mockReset().mockResolvedValue({ data: { configured: true, key_hint: '••••abcd', storage_available: true } });
  api.delete.mockReset().mockResolvedValue({ data: { configured: false, key_hint: null, storage_available: true } });
});

it('saves and replaces an optional key explicitly, only shows its hint, and deletes with an account precondition', async () => {
  const user = userEvent.setup();
  render(<ReferenceSettings userId="account-a" />);
  const input = await screen.findByLabelText('个人 API Key');
  expect(input).toHaveAttribute('type', 'password');
  expect(screen.getByRole('link', { name: /OpenAlex/ })).toHaveAttribute('href', 'https://openalex.org/settings/api');
  await user.type(input, 'private-secret-abcd');
  expect(api.put).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: '保存密钥', exact: true }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('密钥已保存'));
  expect(api.put).toHaveBeenCalledWith(
    '/auth/reference-settings',
    { api_key: 'private-secret-abcd', expected_user_id: 'account-a' },
    expect.any(Object),
  );
  expect(input).toHaveValue('');
  expect(screen.getByText('••••abcd')).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent('private-secret-abcd');
  await user.type(input, 'replacement-efgh');
  await user.click(screen.getByRole('button', { name: '替换密钥', exact: true }));
  await waitFor(() => expect(input).toHaveValue(''));
  await user.click(screen.getByRole('button', { name: '移除密钥', exact: true }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('密钥已移除'));
  expect(api.delete).toHaveBeenCalledWith('/auth/reference-settings', {
    data: { expected_user_id: 'account-a' },
    signal: expect.any(AbortSignal),
  });
  expect(screen.queryByText('••••abcd')).not.toBeInTheDocument();
});

it('uses English copy and disables storage while keeping the fallback explanation available', async () => {
  setLocale('en');
  api.get.mockResolvedValue({ data: { configured: false, key_hint: null, storage_available: false } });
  render(<ReferenceSettings userId="account-a" />);
  expect(await screen.findByText('Secure key storage is temporarily unavailable.')).toBeInTheDocument();
  expect(screen.getByLabelText('Personal API key')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save key', exact: true })).toBeDisabled();
  expect(screen.getByText(/Personal OpenAlex key → platform OpenAlex key → Crossref/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /OpenAlex/ })).toBeInTheDocument();
});

it('discards an old account response and clears typed keys immediately when accounts change', async () => {
  const user = userEvent.setup();
  const view = render(<ReferenceSettings userId="account-a" />);
  const input = await screen.findByLabelText('个人 API Key');
  await user.type(input, 'account-a-secret');
  let finish!: (value: unknown) => void;
  api.put.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await user.click(screen.getByRole('button', { name: '保存密钥', exact: true }));
  view.rerender(<ReferenceSettings userId="account-b" />);
  await waitFor(() => expect(screen.getByLabelText('个人 API Key')).toHaveValue(''));
  await act(async () => finish({ data: { configured: true, key_hint: 'account-a-hint', storage_available: true } }));
  expect(screen.queryByText('account-a-hint')).not.toBeInTheDocument();
  expect(screen.getByLabelText('个人 API Key')).toHaveValue('');
});

it('keeps errors generic even when a rejected request contains a secret', async () => {
  const user = userEvent.setup();
  api.put.mockRejectedValue(new Error('private-secret-in-error'));
  render(<ReferenceSettings userId="account-a" />);
  await user.type(await screen.findByLabelText('个人 API Key'), 'private-secret-in-error');
  await user.click(screen.getByRole('button', { name: '保存密钥', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('操作失败，请重试');
  expect(document.body).not.toHaveTextContent('private-secret-in-error');
});

it('saves and removes SerpAPI independently while preserving the OpenAlex status and draft', async () => {
  const user = userEvent.setup();
  api.get.mockResolvedValue({
    data: {
      configured: true,
      key_hint: '••••alex',
      storage_available: true,
      serpapi_configured: false,
      serpapi_key_hint: null,
    },
  });
  api.put.mockResolvedValue({
    data: {
      configured: true,
      key_hint: '••••alex',
      storage_available: true,
      serpapi_configured: true,
      serpapi_key_hint: '••••serp',
    },
  });
  api.delete.mockResolvedValue({
    data: {
      configured: true,
      key_hint: '••••alex',
      storage_available: true,
      serpapi_configured: false,
      serpapi_key_hint: null,
    },
  });
  render(<ReferenceSettings userId="account-a" />);
  const alex = await screen.findByLabelText('个人 API Key');
  const serp = screen.getByLabelText('SerpAPI 个人密钥');
  expect(serp).toHaveAttribute('type', 'password');
  expect(screen.getByRole('link', { name: /注册 SerpAPI/ })).toHaveAttribute(
    'href',
    'https://serpapi.com/users/sign_up',
  );
  await user.type(alex, 'unsaved-openalex');
  await user.type(serp, 'serp-secret');
  await user.click(screen.getByRole('button', { name: '保存 SerpAPI 密钥', exact: true }));
  await waitFor(() => expect(screen.getByText('••••serp')).toBeInTheDocument());
  expect(api.put).toHaveBeenCalledWith(
    '/auth/reference-settings',
    { serpapi_key: 'serp-secret', expected_user_id: 'account-a' },
    expect.any(Object),
  );
  expect(serp).toHaveValue('');
  expect(alex).toHaveValue('unsaved-openalex');
  await user.click(screen.getByRole('button', { name: '移除 SerpAPI 密钥', exact: true }));
  await waitFor(() => expect(screen.queryByText('••••serp')).not.toBeInTheDocument());
  expect(api.delete).toHaveBeenCalledWith('/auth/reference-settings', {
    data: { provider: 'serpapi', expected_user_id: 'account-a' },
    signal: expect.any(AbortSignal),
  });
  expect(screen.getByText('••••alex')).toBeInTheDocument();
  expect(alex).toHaveValue('unsaved-openalex');
});

it('requires HTTPS before accepting keys while preserving deletion and fallback information', async () => {
  api.get.mockResolvedValue({
    data: {
      configured: true,
      key_hint: '••••alex',
      storage_available: false,
      serpapi_configured: true,
      serpapi_key_hint: '••••serp',
      secure_transport_required: true,
    },
  });
  setLocale('en');
  render(<ReferenceSettings userId="account-a" />);
  expect(await screen.findByText('Use HTTPS to enter API keys.')).toBeInTheDocument();
  expect(screen.getByLabelText('Personal API key')).toBeDisabled();
  expect(screen.getByLabelText('Personal SerpAPI key')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Remove key', exact: true })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Remove SerpAPI key', exact: true })).toBeEnabled();
  expect(screen.getByText(/Personal OpenAlex key → platform OpenAlex key → Crossref/)).toBeInTheDocument();
});

it('aborts a previous account read and never displays its late key hints', async () => {
  let finish!: (value: unknown) => void;
  api.get.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(<ReferenceSettings userId="account-a" />);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  const firstSignal = api.get.mock.calls[0][1].signal;
  view.rerender(<ReferenceSettings userId="account-b" />);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(firstSignal.aborted).toBe(true);
  await act(async () =>
    finish({
      data: {
        configured: true,
        key_hint: 'old-alex',
        storage_available: true,
        serpapi_configured: true,
        serpapi_key_hint: 'old-serp',
      },
    }),
  );
  expect(screen.queryByText('old-alex')).not.toBeInTheDocument();
  expect(screen.queryByText('old-serp')).not.toBeInTheDocument();
  expect(screen.getByLabelText('SerpAPI 个人密钥')).toHaveValue('');
});
