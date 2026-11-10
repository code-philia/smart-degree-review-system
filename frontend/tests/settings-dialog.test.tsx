import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AppearanceProvider } from '../src/AppearanceProvider';
import { MemoryRouter, useNavigate } from 'react-router-dom';
import { SettingsDialog } from '../src/components/SettingsDialog';
import { getLocale, setLocale } from '../src/i18n/locale';

let systemDark = false;
const mediaListeners = new Set<(event: MediaQueryListEvent) => void>();
const media = {
  media: '(prefers-color-scheme: dark)',
  get matches() { return systemDark; },
  onchange: null,
  addListener: (listener: (event: MediaQueryListEvent) => void) => mediaListeners.add(listener),
  removeListener: (listener: (event: MediaQueryListEvent) => void) => mediaListeners.delete(listener),
  addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => mediaListeners.add(listener),
  removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => mediaListeners.delete(listener),
  dispatchEvent: () => true,
};

beforeEach(() => {
  systemDark = false;
  mediaListeners.clear();
  localStorage.clear();
  document.documentElement.classList.remove('light', 'dark');
  setLocale('zh');
  vi.stubGlobal('matchMedia', vi.fn(() => media));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); setLocale('zh'); });

function RouteProbe() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate('/auth')}>Open sign-in</button><button onClick={() => navigate('/paper-upload')}>Open workspace</button></>;
}
function renderSettings(path = '/paper-upload') {
  return render(
    <MemoryRouter initialEntries={[path]}><AppearanceProvider>
      <SettingsDialog open onOpenChange={() => undefined} />
    </AppearanceProvider></MemoryRouter>,
  );
}

it('switches the mounted settings language and persists the chosen locale', async () => {
  const user = userEvent.setup();
  renderSettings();
  expect(screen.getByRole('heading', { name: '设置' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'English', exact: true }));
  expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'English', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: '简体中文', exact: true })).toBeInTheDocument();
  expect(getLocale()).toBe('en');
  expect(localStorage.getItem('sjtu-ui-locale')).toBe('en');
  await user.click(screen.getByRole('button', { name: '简体中文', exact: true }));
  expect(screen.getByRole('heading', { name: '设置' })).toBeInTheDocument();
  expect(getLocale()).toBe('zh');
});

it('defaults to Light and restores Dark from persisted storage after remounting', async () => {
  const user = userEvent.setup();
  const view = renderSettings();
  await waitFor(() => expect(document.documentElement).toHaveClass('light'));
  await user.click(screen.getByRole('button', { name: '深色', exact: true }));
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  expect(localStorage.getItem('sjtu-ui-theme')).toBe('dark');
  view.unmount();
  renderSettings();
  await waitFor(() => expect(screen.getByRole('button', { name: '深色', exact: true })).toHaveAttribute('aria-pressed', 'true'));
  expect(document.documentElement).toHaveClass('dark');
});

it('follows live system appearance changes only while System is selected', async () => {
  const user = userEvent.setup();
  renderSettings();
  await user.click(screen.getByRole('button', { name: '跟随系统', exact: true }));
  expect(localStorage.getItem('sjtu-ui-theme')).toBe('system');
  act(() => {
    systemDark = true;
    mediaListeners.forEach(listener => listener({ matches: true, media: media.media } as MediaQueryListEvent));
  });
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  await user.click(screen.getByRole('button', { name: '浅色', exact: true }));
  act(() => {
    systemDark = false;
    mediaListeners.forEach(listener => listener({ matches: false, media: media.media } as MediaQueryListEvent));
    systemDark = true;
    mediaListeners.forEach(listener => listener({ matches: true, media: media.media } as MediaQueryListEvent));
  });
  await waitFor(() => expect(document.documentElement).toHaveClass('light'));
  expect(localStorage.getItem('sjtu-ui-theme')).toBe('light');
});


it.each(['/auth', '/AUTH', '/Auth/'])('keeps sign-in %s light while preserving the saved workspace appearance', async (path) => {
  localStorage.setItem('sjtu-ui-theme', 'dark');
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={[path]}><AppearanceProvider><RouteProbe /></AppearanceProvider></MemoryRouter>);
  await waitFor(() => expect(document.documentElement).toHaveClass('light'));
  expect(localStorage.getItem('sjtu-ui-theme')).toBe('dark');
  await user.click(screen.getByRole('button', { name: 'Open workspace', exact: true }));
  await waitFor(() => expect(document.documentElement).toHaveClass('dark'));
  await user.click(screen.getByRole('button', { name: 'Open sign-in', exact: true }));
  await waitFor(() => expect(document.documentElement).toHaveClass('light'));
  expect(localStorage.getItem('sjtu-ui-theme')).toBe('dark');
});
