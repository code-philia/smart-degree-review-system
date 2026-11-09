import { afterEach, describe, expect, it, vi } from 'vitest';
import { startPondRenderer } from '../src/pages/authCampus/pondRenderer';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('approved pond renderer pointer path', () => {
  it('disturbs real solver state only for open-water pointer strokes and removes the listener on teardown', () => {
    const gl = new Proxy({
      createShader: () => ({}), createProgram: () => ({}), createBuffer: () => ({}), createTexture: () => ({}),
      getShaderParameter: () => true, getProgramParameter: () => true, getAttribLocation: () => 0,
      getUniformLocation: (_program: unknown, name: string) => name,
    }, { get: (target, key) => key in target ? target[key as keyof typeof target] : /^[A-Z0-9_]+$/.test(String(key)) ? key : () => {} });
    vi.stubGlobal('WebGLRenderingContext', function () {});
    vi.stubGlobal('Image', class {
      naturalWidth=3840; naturalHeight=2160; onload: (() => void)|null=null; onerror=null;
      set src(_value: string) { this.onload?.(); }
    });
    const canvas=document.createElement('canvas'), scene=document.createElement('div');
    vi.spyOn(canvas,'getContext').mockReturnValue(gl as unknown as WebGLRenderingContext);
    vi.spyOn(canvas,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:1920,height:1080} as DOMRect);
    vi.spyOn(window,'getComputedStyle').mockReturnValue({backgroundPosition:'50% 50%',backgroundImage:`url("${window.location.origin}/login-campus-B-v5-b25c6008.png")`} as CSSStyleDeclaration);
    vi.spyOn(window,'requestAnimationFrame').mockReturnValue(11);
    const cancel=vi.spyOn(window,'cancelAnimationFrame');
    const add=vi.spyOn(window,'addEventListener'), remove=vi.spyOn(window,'removeEventListener');
    const clock=vi.spyOn(performance,'now').mockReturnValue(1000);
    const stop=startPondRenderer(canvas,scene);
    try {
      expect(canvas.dataset.renderer).toBe('height-field-webgl');
      expect(canvas.dataset.sourceSize).toBe('3840x2160');
      expect(canvas.dataset.logicalSize).toBe('1672x940.5');
      const handler=add.mock.calls.find(([name]) => name==='pointermove')![1] as EventListener;
      const pointer=(x:number,y:number,target?:Element) => {
        const event=new MouseEvent('pointermove',{clientX:x*1920/1672,clientY:y*1080/940.5});
        if(target) Object.defineProperty(event,'target',{value:target});
        handler(event);
      };
      expect(() => pointer(900,720)).not.toThrow();
      clock.mockReturnValue(1035); pointer(950,730);
      expect(Number(canvas.dataset.cursorStrokes)).toBeGreaterThan(0);
      const strokes=canvas.dataset.cursorStrokes;
      pointer(448,689); clock.mockReturnValue(1070); pointer(460,690);
      expect(canvas.dataset.cursorStrokes).toBe(strokes);
      const card=document.createElement('section');card.className='signin';
      pointer(900,720,card);clock.mockReturnValue(1105);pointer(950,730,card);
      expect(canvas.dataset.cursorStrokes).toBe(strokes);
      stop();expect(remove).toHaveBeenCalledWith('pointermove',handler);
      expect(cancel).toHaveBeenCalledWith(11);
    } finally { stop(); }
  });
});
