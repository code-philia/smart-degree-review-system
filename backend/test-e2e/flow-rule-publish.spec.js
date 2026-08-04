const { test, expect } = require('@playwright/test');

const reqId = 'FLOW-RULE-PUBLISH';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function publishTextLongSentenceRule(page, { scopeLabel, collegeId, threshold, prompt }) {
  await page.goto('/rule-config');
  await expect(page.getByRole('heading', { name: '规范性检测规则配置' })).toBeVisible();
  await expect(page.getByRole('table', { name: '规则配置列表' })).toBeVisible();

  await page.getByLabel('规则作用域').selectOption({ label: scopeLabel });
  if (collegeId) {
    await page.getByLabel('学院编号').fill(collegeId);
  }
  await page.getByLabel('规则编号').fill('TEXT-LONG-SENTENCE');
  await page.getByLabel('规则标题').fill('长句字符阈值');
  await page.getByLabel('类别').fill('文本质量');
  await page.getByLabel('严重程度').selectOption('medium');
  await page.getByLabel('启用状态').selectOption('enabled');
  await page.getByLabel('匹配参数 JSON').fill(JSON.stringify({ max_chars: threshold }));
  await page.getByLabel('提示文案').fill(prompt);
  await page.getByRole('button', { name: '提交生效' }).click();
  await expect(page.getByRole('status')).toContainText('规则已生效');
}

async function getEffectiveTextLongSentenceRule(request, collegeId) {
  const response = await request.get(`/api/normative/rule-configs?level=college&college_id=${collegeId}`);
  expect(response.status()).toBe(200);
  const body = await response.json();
  return body.rules.find((rule) => rule.rule_id === 'TEXT-LONG-SENTENCE' || rule.rule_id === 'NORM-006');
}

test.describe('FLOW-RULE-PUBLISH school and college rule configuration scenarios', () => {
  test('FLOW-RULE-PUBLISH:SCENARIO:001 college rule override takes precedence for college01 while other colleges inherit school value', async ({ browser }) => {
    const schoolContext = await browser.newContext();
    const schoolPage = await schoolContext.newPage();
    await loginAs(schoolPage, 'school_admin01');
    await publishTextLongSentenceRule(schoolPage, {
      scopeLabel: '学校规则',
      threshold: 120,
      prompt: '学校发布 120 字符长句阈值',
    });

    const collegeContext = await browser.newContext();
    const collegePage = await collegeContext.newPage();
    await loginAs(collegePage, 'college_admin01');
    await publishTextLongSentenceRule(collegePage, {
      scopeLabel: '学院规则',
      collegeId: 'college01',
      threshold: 100,
      prompt: 'college01 发布 100 字符长句阈值',
    });

    const college01Rule = await getEffectiveTextLongSentenceRule(collegePage.request, 'college01');
    const college02Rule = await getEffectiveTextLongSentenceRule(schoolPage.request, 'college02');

    expect(college01Rule.source).toBe('college');
    expect(college01Rule.college_id).toBe('college01');
    expect(college01Rule.match_params.max_chars).toBe(100);
    expect(college02Rule.source).toBe('school');
    expect(college02Rule.match_params.max_chars).toBe(120);
    await collegeContext.close();
    await schoolContext.close();
  });

  test('FLOW-RULE-PUBLISH:SCENARIO:002 college01 administrator is rejected from modifying college02 and college02 rule remains unchanged', async ({ browser }) => {
    const schoolContext = await browser.newContext();
    const schoolPage = await schoolContext.newPage();
    await loginAs(schoolPage, 'school_admin01');
    await publishTextLongSentenceRule(schoolPage, {
      scopeLabel: '学校规则',
      threshold: 120,
      prompt: 'college02 继承的学校规则保持不变',
    });
    const beforeRule = await getEffectiveTextLongSentenceRule(schoolPage.request, 'college02');

    const collegeContext = await browser.newContext();
    const collegePage = await collegeContext.newPage();
    await loginAs(collegePage, 'college_admin01');
    await collegePage.goto('/rule-config');
    await expect(collegePage.getByText(/当前登录用户：college_admin01（COLLEGE_ADMIN）/)).toBeVisible();

    const forbiddenResponse = await collegePage.request.put('/api/normative/rule-configs', {
      data: {
        scope: { level: 'college', college_id: 'college02' },
        rule: {
          rule_id: 'TEXT-LONG-SENTENCE',
          title: '长句字符阈值',
          category: '文本质量',
          severity: 'medium',
          enabled: true,
          match_params: { max_chars: 80 },
          prompt: '非法跨学院修改',
        },
      },
    });
    expect(forbiddenResponse.status()).toBe(403);

    const afterRule = await getEffectiveTextLongSentenceRule(schoolPage.request, 'college02');
    expect(afterRule.match_params.max_chars).toBe(beforeRule.match_params.max_chars);
    expect(afterRule.prompt).toBe(beforeRule.prompt);
    await collegeContext.close();
    await schoolContext.close();
  });
});
