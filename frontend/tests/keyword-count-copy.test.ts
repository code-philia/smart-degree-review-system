import { afterEach, expect, it } from 'vitest';
import { setLocale, translate, hasTranslation } from '../src/i18n/locale';
import registry from '../../backend/rules/registry.json';

const description='按最新国标要求检查中英文关键词是否少于3个或多于8个。';
const message=(n:number)=>`关键词共${n}个，按最新国标要求关键词为3-8个，该范围为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新。`;
afterEach(()=>setLocale('zh'));
it('publishes the requested bilingual keyword description in the real catalog',()=>{
 const rules=Array.isArray(registry)?registry:(registry as any).rules;
 expect(rules.find((r:any)=>r.rule_id==='keyword_count_check').description).toBe(description);
});
it('translates the description and title without a model request',()=>{
 setLocale('en');expect(translate(description)).toBe('Check whether the Chinese or English keyword list contains fewer than 3 or more than 8 keywords, following the latest national standard.');
 expect(translate('关键词数量')).toBe('Keyword count');
});
it.each([0,1,2,9,12])('translates the complete advisory for %s keywords deterministically',n=>{
 setLocale('en');expect(hasTranslation(message(n),'en')).toBe(true);
 expect(translate(message(n))).toBe(`The list contains ${n} ${n===1?'keyword':'keywords'}. The latest national standard recommends 3–8 keywords. This range is a recommendation to improve quality, not a mandatory validation requirement. The university thesis template will be updated accordingly.`);
 setLocale('zh');expect(translate(message(n))).toBe(message(n));
});
