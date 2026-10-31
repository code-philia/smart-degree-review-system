import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AuthPage from '../src/pages/AuthPage';
import { isInPool, poolLeft, POOL_PATH, WaterWaveSolver } from '../src/pages/authCampus/waterSurface';

describe('selected Siyuan sign-in scene', () => {
  it('ships the selected illustration without preview or motion toggles', () => {
    render(<AuthPage accountFormSlot={<form aria-label="Real login" />} helpSlot={<p>Account help</p>} />);
    expect(document.querySelector('img[src="/sjtu-siyuan-illustration.webp"]')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /暂停|开启.*动效|选用此方案/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /使用 jAccount 登录/ })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.getByRole('form', { name: 'Real login' })).toBeInTheDocument();
    expect(screen.getByText('Account help')).toBeInTheDocument();
    expect(document.querySelectorAll('.campus-wind-leaf')).toHaveLength(5);
  });
  it('supports keyboard gear activation and cancels its frame on unmount', () => {
    const request = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(73);
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const view = render(<AuthPage />);
    fireEvent.keyDown(screen.getByRole('button', { name: '点击齿轮，旋转两圈' }), { key: 'Enter' });
    expect(screen.getByRole('button', { name: '齿轮正在旋转' })).toHaveAttribute('aria-disabled', 'true');
    view.unmount();
    expect(cancel).toHaveBeenCalledWith(73);
    request.mockRestore();
    cancel.mockRestore();
  });
  it('preserves the remaining gear rotation while the page is hidden', () => {
    const request = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(91);
    const cancel = vi.spyOn(window, 'cancelAnimationFrame');
    const clock = vi.spyOn(performance, 'now').mockReturnValue(100);
    const hidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    const view = render(<AuthPage />);
    try {
      fireEvent.click(screen.getByRole('button', { name: '点击齿轮，旋转两圈' }));
      act(() => request.mock.calls.at(-1)![0](1100));
      const before = document.querySelector('.campus-gear-rotor')!.getAttribute('transform');
      clock.mockReturnValue(1100);
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      fireEvent(document, new Event('visibilitychange'));
      expect(cancel).toHaveBeenCalledWith(91);
      clock.mockReturnValue(9100);
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      fireEvent(document, new Event('visibilitychange'));
      act(() => request.mock.calls.at(-1)![0](9100));
      expect(document.querySelector('.campus-gear-rotor')).toHaveAttribute('transform', before);
      expect(screen.getByRole('button', { name: '齿轮正在旋转' })).toBeInTheDocument();
    } finally {
      view.unmount();
      if (hidden) Object.defineProperty(document, 'hidden', hidden);
      else Reflect.deleteProperty(document, 'hidden');
      request.mockRestore();
      cancel.mockRestore();
      clock.mockRestore();
    }
  });
});
describe('pond surface boundaries and dynamics', () => {
  it.each([
    [40, 800],
    [150, 850],
    [340, 920],
    [460, 935],
    [700, 725],
  ])('excludes pavement/shore at %s,%s', (x, y) => {
    expect(isInPool(x, y)).toBe(false);
  });
  it.each([
    [600, 790],
    [700, 870],
    [820, 920],
  ])('keeps open water interactive at %s,%s', (x, y) => {
    expect(isInPool(x, y)).toBe(true);
  });
  it('uses the same bank coordinates for pointer and SVG clipping', () => {
    expect(poolLeft(885)).toBe(340);
    expect(POOL_PATH).toContain('L340 885');
  });
  it('propagates then settles a bounded cursor wake', () => {
    const field = new WaterWaveSolver(256, 112);
    field.stroke({ x: 0.4, y: 0.5 }, { x: 0.43, y: 0.51 });
    expect(field.energy()).toBeGreaterThan(0);
    const initiallyEmpty = Array.from(field.height)
      .map((h, i) => (Math.abs(h) < 1e-9 ? i : -1))
      .filter((i) => i >= 0);
    for (let i = 0; i < 90; i++) field.step();
    expect(initiallyEmpty.some((i) => Math.abs(field.height[i]) > 1e-5)).toBe(true);
    const moving = field.energy();
    for (let i = 0; i < 1600; i++) field.step();
    expect(field.energy()).toBeLessThan(moving * 0.02);
    expect(Array.from(field.height).every((h) => Number.isFinite(h) && Math.abs(h) <= 0.65001)).toBe(true);
  });
});
