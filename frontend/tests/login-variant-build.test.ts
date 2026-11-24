import { describe, expect, it } from 'vitest';
import { resolveLoginVariant } from '../build/loginVariant';

describe('delivery login selection', () => {
  it('defaults to the existing campus login for ordinary builds', () => {
    expect(resolveLoginVariant(undefined)).toBe('campus');
    expect(resolveLoginVariant('')).toBe('campus');
  });
  it.each(['campus', 'split'])('accepts the explicit %s selection', value => {
    expect(resolveLoginVariant(value)).toBe(value);
  });
  it('uses the committed delivery selection for the normal publisher and allows a comparison override', () => {
    expect(resolveLoginVariant(undefined, 'split')).toBe('split');
    expect(resolveLoginVariant('campus', 'split')).toBe('campus');
    expect(() => resolveLoginVariant(undefined, 'unknown')).toThrow(/VITE_LOGIN_VARIANT/);
  });
  it.each(['formal', 'Split', '../split', 'campus,split'])('rejects unknown selection %s instead of silently shipping a different login', value => {
    expect(() => resolveLoginVariant(value)).toThrow(/VITE_LOGIN_VARIANT/);
  });
});
