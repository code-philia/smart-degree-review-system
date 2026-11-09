import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AuthPage from '../src/pages/AuthPage';
import { isInPool, waterMaskAlpha, sourcePoint, WaterWaveSolver } from '../src/pages/authCampus/waterSurface';

describe('approved B-v5 sign-in scene', () => {
  it('ships the approved scene, filing number and real login without gear interaction', () => {
    render(<AuthPage />);
    expect(document.querySelector('.scene')).toBeInTheDocument();
    expect(screen.getByRole('contentinfo', { name: '网站备案信息' })).toHaveTextContent('沪交ICP备20260352');
    expect(screen.getAllByText('沪交ICP备20260352')).toHaveLength(1);
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.queryByRole('button', { name: /齿轮/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('form')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.breeze-leaf')).toHaveLength(5);
    expect(document.querySelectorAll('.breeze-grass g')).toHaveLength(2);
    expect(screen.queryByText(/视觉设计稿|登录按钮仅供展示/)).not.toBeInTheDocument();
  });
  it('honors live reduced-motion changes and stops wind when the page is hidden', () => {
    const media = Object.assign(new EventTarget(), { matches: false });
    vi.stubGlobal('matchMedia', () => media);
    const view = render(<AuthPage />);
    const layer = document.querySelector('.preview-breeze')!;
    const canvas = document.querySelector('canvas')!;
    const hidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    try {
      expect(layer).toHaveAttribute('data-active', 'true');
      act(() => { media.matches = true; media.dispatchEvent(new Event('change')); });
      expect(layer).toHaveAttribute('data-active', 'false');
      expect(canvas.hidden).toBe(true);
      act(() => { media.matches = false; media.dispatchEvent(new Event('change')); });
      expect(layer).toHaveAttribute('data-active', 'true');
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      fireEvent(document, new Event('visibilitychange'));
      expect(layer).toHaveAttribute('data-active', 'false');
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      fireEvent(document, new Event('visibilitychange'));
      expect(layer).toHaveAttribute('data-active', 'true');
      view.unmount();
      act(() => { media.matches = true; media.dispatchEvent(new Event('change')); });
    } finally {
      view.unmount();
      if (hidden) Object.defineProperty(document, 'hidden', hidden);
      else Reflect.deleteProperty(document, 'hidden');
      vi.unstubAllGlobals();
    }
  });
});
describe('B-v5 water-only boundaries and dynamics', () => {
  it.each([
    ['monument',460,550],['plinth',460,637],['far bank',850,618],['cup',130,700],
    ['cup lower',140,750],['pen cap',249,694],['pen',265,722],['writing wrist',200,758],
    ['writing fingers',270,795],['forearm',347,725],['seal hand',448,689],['knuckle',490,669],
    ['turning finger',570,731],['thumb',514,727],['left page',430,822],['turned page',565,798],
    ['table',750,880],['near bank',1200,839],['near bank right',1600,875],['flowers',100,866],
  ])('keeps %s static', (_name, x, y) => { expect(isInPool(Number(x),Number(y))).toBe(false); });
  it.each([[200,650],[300,652],[700,678],[1100,760],[1500,800],[415,746]])(
    'keeps visible water interactive at %s,%s', (x,y) => { expect(isInPool(x,y)).toBe(true); },
  );
  it('feathers the narrow water gap without routing pointer ripples through the finger edge', () => {
    expect(waterMaskAlpha(541,723)).toBeGreaterThan(0);
    expect(waterMaskAlpha(541,723)).toBeLessThan(1);
    expect(isInPool(541,723)).toBe(false);
  });
  it.each([[1920,1080],[1536,864],[1440,900],[1280,720],[390,844],[844,390],[1920,600]])(
    'maps the exact 4K cover image to the water mask at %s x %s', (width,height) => {
      const position=width<=704?{x:.47,y:.42}:{x:.5,y:.5};
      const scale=Math.max(width/3840,height/2160);
      for(const [x,y] of [[900,730],[448,689],[1450,820]]) {
        const clientX=x*3840/1672*scale+(width-3840*scale)*position.x;
        const clientY=y*2160/940.5*scale+(height-2160*scale)*position.y;
        const point=sourcePoint(clientX,clientY,{left:0,top:0,width,height},position);
        expect(point.x).toBeCloseTo(x,8); expect(point.y).toBeCloseTo(y,8);
      }
    },
  );
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
