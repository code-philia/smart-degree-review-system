const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-INNOVATION-ANALYZE';
void reqId;

const demoPassword = 'ArcDemo123!';

function longText(label) {
  return `${label}证据围绕论文创新性评估展开，包含可核验资料和论证依据，超过二十个字符。`;
}

const scenarioPayload = {
  thesis_title: '高校数字治理创新机制研究',
  degree_type: 'master',
  primary_discipline: '管理学',
  secondary_discipline: '公共管理',
  research_direction: '高校数字治理',
  dimensions: {
    research_topic: {
      level: 5,
      evidence: longText('研究选题'),
      improvement_plan: '研究选题改进计划将补充前沿文献和政策场景，增强问题意识。',
    },
    research_method: {
      level: 4,
      evidence: longText('研究方法'),
      improvement_plan: '研究方法改进计划将增加访谈样本和三角验证，提升方法可靠性。',
    },
    research_content: {
      level: 4,
      evidence: longText('研究内容'),
      improvement_plan: '研究内容改进计划将扩展案例比较和数据解释，增强论证深度。',
    },
    research_conclusion: {
      level: 3,
      evidence: longText('研究结论'),
      improvement_plan: '研究结论改进计划将明确适用边界和进一步研究方向，减少泛化。',
    },
    application_value: {
      level: 4,
      evidence: longText('应用价值'),
      improvement_plan: '应用价值改进计划将设计落地指标和推广条件，提升实践可用性。',
    },
  },
};

async function loginAsStudent(page) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText('已登录：student01（STUDENT）')).toBeVisible();
}

async function fillScenarioForm(page, payload) {
  await page.getByLabel('论文题目').fill(payload.thesis_title);
  await page.getByLabel('学历层次').selectOption(payload.degree_type);
  await page.getByLabel('一级学科').fill(payload.primary_discipline);
  await page.getByLabel('二级学科').fill(payload.secondary_discipline);
  await page.getByLabel('研究方向').fill(payload.research_direction);

  await page.getByLabel('研究选题等级').selectOption(String(payload.dimensions.research_topic.level));
  await page.getByLabel('研究选题证据').fill(payload.dimensions.research_topic.evidence);
  await page.getByLabel('研究选题改进计划').fill(payload.dimensions.research_topic.improvement_plan);

  await page.getByLabel('研究方法等级').selectOption(String(payload.dimensions.research_method.level));
  await page.getByLabel('研究方法证据').fill(payload.dimensions.research_method.evidence);
  await page.getByLabel('研究方法改进计划').fill(payload.dimensions.research_method.improvement_plan);

  await page.getByLabel('研究内容等级').selectOption(String(payload.dimensions.research_content.level));
  await page.getByLabel('研究内容证据').fill(payload.dimensions.research_content.evidence);
  await page.getByLabel('研究内容改进计划').fill(payload.dimensions.research_content.improvement_plan);

  await page.getByLabel('研究结论等级').selectOption(String(payload.dimensions.research_conclusion.level));
  await page.getByLabel('研究结论证据').fill(payload.dimensions.research_conclusion.evidence);
  await page.getByLabel('研究结论改进计划').fill(payload.dimensions.research_conclusion.improvement_plan);

  await page.getByLabel('应用价值等级').selectOption(String(payload.dimensions.application_value.level));
  await page.getByLabel('应用价值证据').fill(payload.dimensions.application_value.evidence);
  await page.getByLabel('应用价值改进计划').fill(payload.dimensions.application_value.improvement_plan);
}

test.describe('FEAT-INNOVATION-ANALYZE innovation self-assessment scenarios', () => {
  test('FEAT-INNOVATION-ANALYZE:SCENARIO:001 student completes five-dimension assessment and a persisted snapshot is visible and readable through the API', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/innovation-assessment');

    await expect(page.getByRole('heading', { name: '发起创新性量表评估' })).toBeVisible();
    await expect(page.getByText('本结果为量表自评，不代替专家评审或文献查新')).toBeVisible();
    await expect(page.getByText(/当前登录用户：student01（STUDENT）/)).toBeVisible();
    await expect(page.getByRole('heading', { name: '分析结果' })).toHaveCount(0);

    await fillScenarioForm(page, scenarioPayload);
    await page.getByRole('button', { name: 'AI 创新性分析' }).click();

    await expect(page.getByRole('heading', { name: '分析结果' })).toBeVisible();
    await expect(page.getByText(scenarioPayload.thesis_title)).toBeVisible();
    await expect(page.getByText('80 分')).toBeVisible();
    await expect(page.getByText('良好')).toBeVisible();
    await expect(page.getByRole('progressbar', { name: '创新性量表评估进度' })).toHaveAttribute('aria-valuenow', '100');
    await expect(page.getByText(/保存编号：/)).toBeVisible();

    const detailTable = page.getByRole('table', { name: '创新性量表分项分' });
    await expect(detailTable.getByText('研究选题')).toBeVisible();
    await expect(detailTable.getByText('研究方法')).toBeVisible();
    await expect(detailTable.getByText('20%')).toHaveCount(3);
    await expect(detailTable.getByText('25%')).toBeVisible();
    await expect(detailTable.getByText('15%')).toBeVisible();
    await expect(detailTable.getByText('16')).toBeVisible();

    const apiResponse = await page.request.post('/api/normative/innovation-assessments', {
      data: {
        ...scenarioPayload,
        thesis_title: `${scenarioPayload.thesis_title} API 复核`,
      },
    });
    expect(apiResponse.status()).toBe(201);
    const apiBody = await apiResponse.json();
    expect(apiBody.id).toEqual(expect.any(String));
    expect(apiBody.input_snapshot.dimensions.research_method.evidence).toContain('研究方法');
    expect(apiBody.scoring_snapshot.dimensions).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'research_method', weight: 0.2, weighted_score: 16 }),
    ]));
    expect(apiBody.total_score).toBe(80);
    expect(apiBody.grade_label).toBe('良好');
  });

  test('FEAT-INNOVATION-ANALYZE:SCENARIO:002 student sees research-method evidence error and no assessment is saved', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/innovation-assessment');

    const invalidPayload = {
      ...scenarioPayload,
      dimensions: {
        ...scenarioPayload.dimensions,
        research_method: {
          ...scenarioPayload.dimensions.research_method,
          evidence: '证据不足',
        },
      },
    };

    await fillScenarioForm(page, invalidPayload);
    await page.getByRole('button', { name: 'AI 创新性分析' }).click();

    await expect(page.getByText(/研究方法证据不完整/)).toBeVisible();
    await expect(page.getByRole('heading', { name: '分析结果' })).toHaveCount(0);
    await expect(page.getByText(/保存编号：/)).toHaveCount(0);

    const apiResponse = await page.request.post('/api/normative/innovation-assessments', {
      data: invalidPayload,
    });
    expect(apiResponse.status()).toBe(400);
    const apiBody = await apiResponse.json();
    expect(apiBody.errors).toEqual(expect.arrayContaining([
      expect.objectContaining({ field: 'dimensions.research_method.evidence' }),
    ]));
    expect(apiBody.id).toBeUndefined();
  });

  test('FEAT-INNOVATION-ANALYZE anonymous users cannot create assessments through the UI route or API boundary', async ({ page }) => {
    await page.goto('/innovation-assessment');

    await expect(page.getByRole('heading', { name: '发起创新性量表评估' })).toBeVisible();
    await expect(page.getByText(/请先登录后发起创新性量表评估/)).toBeVisible();
    await expect(page.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    await expect(page.getByRole('button', { name: 'AI 创新性分析' })).toHaveCount(0);

    const response = await page.request.post('/api/normative/innovation-assessments', {
      data: scenarioPayload,
    });
    expect(response.status()).toBe(401);
  });
});
