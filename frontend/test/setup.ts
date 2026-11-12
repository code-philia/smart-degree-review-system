import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Existing UI fixtures exercise the Chinese reference interface. Language
// detection tests explicitly override these browser preferences.
Object.defineProperties(navigator, {
  language: { configurable: true, get: () => 'zh-CN' },
  languages: { configurable: true, get: () => ['zh-CN'] },
});

// jsdom has no module workers; PDF rendering is isolated in the viewer tests.
if (!globalThis.Worker) {
  globalThis.Worker = class extends EventTarget {
    postMessage() {}
    terminate() {}
  } as unknown as typeof Worker;
}

if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => undefined;
}

if (!globalThis.ResizeObserver) {
  class ResizeObserverMock {
    observe() {}

    unobserve() {}

    disconnect() {}
  }

  Object.defineProperty(globalThis, 'ResizeObserver', {
    configurable: true,
    value: ResizeObserverMock,
  });
}

afterEach(() => {
  cleanup();
});
