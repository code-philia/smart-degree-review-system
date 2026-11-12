import {afterEach,beforeEach,expect,it,vi} from 'vitest';
beforeEach(()=>{vi.resetModules();localStorage.clear();window.history.replaceState({},'','/auth');});
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear();window.history.replaceState({},'','/');});
it.each([['zh-CN','zh'],['zh-TW','zh'],['en-US','en'],['fr-FR','en'],['','zh']])('initializes an unchosen browser language %s as %s',async(language,expected)=>{
 vi.stubGlobal('navigator',{language,languages:language?[language]:[]});
 const locale=await import('../src/i18n/locale');expect(locale.getLocale()).toBe(expected);
 expect(localStorage.getItem('sjtu-ui-locale')).toBeNull();
});
it('preserves a legacy saved manual choice ahead of browser detection',async()=>{
 localStorage.setItem('sjtu-ui-locale','zh');vi.stubGlobal('navigator',{language:'en-US',languages:['en-US']});
 const locale=await import('../src/i18n/locale');expect(locale.getLocale()).toBe('zh');
});
it('resolves an explicit email link before the initial render',async()=>{
 localStorage.setItem('sjtu-ui-locale','zh');window.history.replaceState({},'','/auth?lang=en');
 const locale=await import('../src/i18n/locale');expect(locale.getLocale()).toBe('en');
 expect(localStorage.getItem('sjtu-ui-locale')).toBe('zh');
});
