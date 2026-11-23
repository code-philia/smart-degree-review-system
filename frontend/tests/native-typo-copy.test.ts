import {afterEach,expect,it} from 'vitest';
import {setLocale,translate} from '../src/i18n/locale';
const message='未识别到可检测的原生正文；扫描页不参与错别字检测，且不使用OCR。';
afterEach(()=>setLocale('zh'));
it('explains native-only typo coverage in both languages',()=>{
 setLocale('zh');expect(translate(message)).toBe(message);
 setLocale('en');expect(translate(message)).toBe('No readable native body text was found for this check. Scanned pages are excluded from character-error checks, and OCR is not used.');
});
