import {afterEach,expect,it,vi} from 'vitest';
afterEach(()=>{window.history.replaceState({},'','/');localStorage.clear();vi.resetModules();});
it.each([['zh','en'],['en','zh']])('gives explicit %s link language priority over stored %s before rendering',async(lang,stored)=>{
 vi.resetModules();localStorage.setItem('sjtu-ui-locale',stored);window.history.replaceState({},'','/reports/pdf/report-1?lang='+lang);
 const locale=await import('../src/i18n/locale');expect(locale.getLocale()).toBe(lang);expect(document.documentElement.lang).toBe(lang==='en'?'en':'zh-CN');
});
it.each(['?lang=fr','?lang=en&lang=zh','?LANG=en',''])('preserves the preference for an absent or invalid language %s',async search=>{
 vi.resetModules();localStorage.setItem('sjtu-ui-locale','zh');window.history.replaceState({},'','/reports/pdf/report-1'+search);
 expect((await import('../src/i18n/locale')).getLocale()).toBe('zh');
});
