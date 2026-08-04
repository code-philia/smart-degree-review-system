const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-RULE-TEMPLATE-UPLOAD';
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

function validRuleDrafts() {
  return [
    {
      rule_id: 'E2E-UPLOAD-001',
      title: '标题完整性',
      category: '结构规范',
      severity: '严重',
      enabled: true,
      message: '标题必须完整',
      params: { required: true },
    },
    {
      rule_id: 'E2E-UPLOAD-002',
      title: '参考文献格式',
      category: '引用规范',
      severity: '一般',
      enabled: false,
      message: '参考文献格式需统一',
    },
  ];
}

async function setRuleDraftFile(page, drafts) {
  const fileInput = page.locator('input[name="ruleDraftTemplate"]');
  await fileInput.setInputFiles({
    name: 'rule-drafts.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(drafts), 'utf8'),
  });
}

async function getTextLongSentenceRule(request) {
  const response = await request.get('/api/normative/rule-configs?level=school');
  expect(response.status()).toBe(200);
  const body = await response.json();
  return body.rules.find((rule) => rule.rule_id === 'TEXT-LONG-SENTENCE' || rule.rule_id === 'NORM-006');
}

test.describe('FEAT-RULE-TEMPLATE-UPLOAD JSON rule draft import scenarios', () => {
  test('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:001 school admin imports two valid JSON rules as drafts without changing active rules', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await page.goto('/rule-config');
    await expect(page.getByRole('heading', { name: '规范性检测规则配置' })).toBeVisible();
    await expect(page.getByText(/JSON 规则集导入草稿/)).toBeVisible();
    await expect(page.getByText(/仅保存为规则草稿，不会自动生效/)).toBeVisible();
    await expect(page.getByText(/DOC\/DOCX 模板不支持自动推导规则/)).toBeVisible();

    const activeRuleBefore = await getTextLongSentenceRule(page.request);

    await setRuleDraftFile(page, validRuleDrafts());
    await page.getByRole('button', { name: '导入规则草稿' }).click();

    await expect(page.getByRole('status')).toContainText('已创建 2 条规则草稿');
    await expect(page.getByRole('status')).toContainText('未改变已生效规则');

    const activeRuleAfter = await getTextLongSentenceRule(page.request);
    expect(activeRuleAfter.match_params).toEqual(activeRuleBefore.match_params);
    expect(activeRuleAfter.prompt).toBe(activeRuleBefore.prompt);
  });

  test('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:002 college admin sees item-indexed errors for invalid JSON and no partial success', async ({ page }) => {
    await loginAs(page, 'college_admin01');
    await page.goto('/rule-config');
    await expect(page.getByText(/当前登录用户：college_admin01（COLLEGE_ADMIN）/)).toBeVisible();

    await setRuleDraftFile(page, [
      {
        title: '缺少规则编号',
        category: '结构规范',
        severity: '严重',
        enabled: true,
        message: '缺少 rule_id',
      },
      {
        rule_id: 'E2E-UPLOAD-BAD-SEVERITY',
        title: '非法严重程度',
        category: '结构规范',
        severity: '紧急',
        enabled: true,
        message: 'severity 不在允许范围',
      },
    ]);
    await page.getByRole('button', { name: '导入规则草稿' }).click();

    await expect(page.getByText(/第 0 项|item_index.*0|item 0|索引 0/)).toBeVisible();
    await expect(page.getByText(/rule_id/)).toBeVisible();
    await expect(page.getByText(/第 1 项|item_index.*1|item 1|索引 1/)).toBeVisible();
    await expect(page.getByText(/severity|严重、一般、轻微/)).toBeVisible();
    await expect(page.getByText(/已创建 .* 条规则草稿/)).not.toBeVisible();
  });
});
