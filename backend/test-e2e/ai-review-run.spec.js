const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AI-REVIEW-RUN';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAsStudent(page) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText('已登录：student01（STUDENT）')).toBeVisible();
}

function buildReferenceLines(count) {
  return Array.from({ length: count }, (_, index) => `[${index + 1}] 引用条目 ${index + 1}`).join('\n');
}

function buildMissingConclusionText(referenceCount = 50) {
  return [
    '摘要',
    '关键词',
    '引言',
    '研究方法',
    '分析与讨论',
    '参考文献',
    buildReferenceLines(referenceCount),
  ].join('\n');
}

test.describe('FEAT-AI-REVIEW-RUN rule-based auxiliary review scenario', () => {
  test('FEAT-AI-REVIEW-RUN:SCENARIO:001 student01 submits a paper missing 结论 and sees a 需修改 result with the missing section called out', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/ai-review');

    await expect(page.getByRole('heading', { name: 'AI 智能评阅' })).toBeVisible();
    await expect(page.getByRole('button', { name: '智能评阅' })).toBeVisible();

    await page.getByRole('button', { name: '学术型硕士' }).click();
    await page.getByLabel('论文题目').fill('高校数字治理平台评阅研究');
    await page.getByLabel('论文文本').fill(buildMissingConclusionText());
    await page.getByRole('button', { name: '智能评阅' }).click();

    await expect(page.getByRole('heading', { name: '评阅结果' })).toBeVisible();
    await expect(page.getByText(/需修改/)).toBeVisible();
    await expect(page.getByText('缺失章节：结论')).toBeVisible();

    const apiResponse = await page.request.post('/api/normative/ai-review-runs', {
      data: {
        thesis_title: '高校数字治理平台评阅研究',
        template_id: 'academic_master',
        text: buildMissingConclusionText(),
        source_type: 'paste',
      },
    });
    expect(apiResponse.status()).toBe(201);
    const apiBody = await apiResponse.json();
    expect(apiBody.result_label).toBe('需修改');
    expect(apiBody.missing_sections).toEqual(['结论']);
    expect(apiBody.score_items.find((item) => item.key === 'conclusion_section').score).toBe(0);
    expect(apiBody.score_items.find((item) => item.key === 'conclusion_section').findings).toContain('缺少结论章节');
  });
});
