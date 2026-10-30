// PDF.js 5 uses the ES2024 Uint8Array byte helpers. Older Chromium/Edge
// versions do not expose them yet, so install a local, non-enumerable fallback.
const urlConstructor = URL as typeof URL & {
  parse?: (input: string, base?: string | URL) => URL | null;
};

if (typeof urlConstructor.parse !== 'function') {
  Object.defineProperty(urlConstructor, 'parse', {
    configurable: true,
    value(input: string, base?: string | URL) {
      try {
        return new URL(input, base);
      } catch {
        return null;
      }
    },
  });
}

const bytes = Uint8Array.prototype as Uint8Array & {
  toHex?: () => string;
  toBase64?: () => string;
};

if (typeof bytes.toHex !== 'function') {
  Object.defineProperty(bytes, 'toHex', {
    configurable: true,
    value(this: Uint8Array) {
      let output = '';
      for (const value of this) output += value.toString(16).padStart(2, '0');
      return output;
    },
  });
}

if (typeof bytes.toBase64 !== 'function') {
  Object.defineProperty(bytes, 'toBase64', {
    configurable: true,
    value(this: Uint8Array) {
      let binary = '';
      const chunk = 0x8000;
      for (let offset = 0; offset < this.length; offset += chunk) {
        binary += String.fromCharCode(...this.subarray(offset, offset + chunk));
      }
      return btoa(binary);
    },
  });
}
