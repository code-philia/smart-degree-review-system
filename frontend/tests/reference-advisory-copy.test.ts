import { afterEach, expect, it } from 'vitest';
import { setLocale, translate, hasTranslation } from '../src/i18n/locale';
import { resolveReportProseText } from '../src/i18n/ReportProse';

const message='按最新参考文献标准GB/T 7714-2025，文献类型或载体标记不在国标代码表中';
const suggestion='可按最新国家标准根据实际著录资源核对并补齐类型标记，所有参考文献标准统一用GB/T 7714-2025或GB/T 7714-2015，该检测项为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新';
afterEach(()=>setLocale('zh'));
it('preserves the exact requested Chinese message and suggestion',()=>{
  setLocale('zh');expect(resolveReportProseText({text:message})).toBe(message);
  expect(resolveReportProseText({text:suggestion})).toBe(suggestion);
});
it('translates the full invalid-code explanation deterministically',()=>{
  setLocale('en');expect(hasTranslation(message,'en')).toBe(true);
  expect(translate(message)).toBe('Under the latest reference standard, GB/T 7714-2025, the document type or medium code is not listed in the national standard’s code table.');
});
it('retains both standard editions and the complete advisory qualification in English',()=>{
  setLocale('en');expect(hasTranslation(suggestion,'en')).toBe(true);
  expect(resolveReportProseText({text:suggestion})).toBe('Check and complete the type code according to the resource actually cited and the latest national standard. Use either GB/T 7714-2025 or GB/T 7714-2015 consistently throughout the reference list. This check is a recommendation to improve quality, not a mandatory validation requirement. The university thesis template will be updated accordingly.');
});
