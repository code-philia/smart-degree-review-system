const { readFile } = require('node:fs/promises');
const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-INNOVATION-REPORT';
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
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(/已登录：student01（STUDENT）/)).toBeVisible();
}

async function createCompletedInnovationAssessment(page) {
  const response = await page.request.post('/api/normative/innovation-assessments', {
    data: scenarioPayload,
  });
  expect(response.status()).toBe(201);
  const report = await response.json();
  expect(report.id).toEqual(expect.any(String));
  expect(report.total_score).toBe(80);
  expect(report.grade_label).toBe('良好');
  return report;
}

async function expectDimensionConsistency(page, dimension) {
  const textRegion = page.getByTestId(`innovation-report-dimension-text-${dimension.key}`);
  const chartRegion = page.getByTestId(`innovation-report-radar-dimension-${dimension.key}`);
  const heatCell = page.getByTestId(`innovation-report-heatmap-dimension-${dimension.key}`);

  await expect(textRegion).toContainText(dimension.label);
  await expect(textRegion).toContainText(`等级 ${dimension.level}`);
  await expect(textRegion).toContainText(`原始分 ${dimension.raw_score}`);
  await expect(textRegion).toContainText(`权重 ${Math.round(dimension.weight * 100)}%`);
  await expect(textRegion).toContainText(`加权分 ${dimension.weighted_score}`);
  await expect(chartRegion).toHaveAttribute('data-level', String(dimension.level));
  await expect(chartRegion).toHaveAttribute('data-weighted-score', String(dimension.weighted_score));
  await expect(heatCell).toHaveAttribute('data-level', String(dimension.level));
  await expect(heatCell).toHaveAttribute('data-weighted-score', String(dimension.weighted_score));
}

test.describe('FEAT-INNOVATION-REPORT transparent scoring report scenario', () => {
  test('FEAT-INNOVATION-REPORT:SCENARIO:001 student opens a completed assessment report with matching text, chart values, JSON download, and print control', async ({ page }) => {
    await loginAsStudent(page);
    const report = await createCompletedInnovationAssessment(page);

    await page.goto(`/innovation-assessments/${report.id}`);
    await expect(page.getByRole('heading', { name: '学位论文创新性分析报告' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: '创新性报告章节' })).toBeVisible();
    await expect(page.getByRole('button', { name: '基本信息' })).toBeVisible();
    await expect(page.getByRole('button', { name: '核心指标雷达图' })).toBeVisible();
    await expect(page.getByRole('button', { name: '子指标热力图' })).toBeVisible();
    await expect(page.getByRole('button', { name: '分项评价' })).toBeVisible();
    await expect(page.getByRole('button', { name: '综合评价与建议' })).toBeVisible();

    await expect(page.getByText('第一部分 · 基本信息')).toBeVisible();
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText(scenarioPayload.thesis_title);
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText('student01');
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText(scenarioPayload.primary_discipline);
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText(scenarioPayload.secondary_discipline);
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText(scenarioPayload.research_direction);
    await expect(page.getByTestId('innovation-report-total-score')).toContainText(String(report.total_score));
    await expect(page.getByTestId('innovation-report-grade')).toContainText(report.grade_label);

    await page.getByRole('button', { name: '核心指标雷达图' }).click();
    await expect(page.getByText('第二部分 · 核心指标雷达图')).toBeVisible();
    await expect(page.getByRole('img', { name: '五维创新性雷达图' })).toBeVisible();

    await page.getByRole('button', { name: '子指标热力图' }).click();
    await expect(page.getByText('第三部分 · 子指标热力图')).toBeVisible();
    await expect(page.getByRole('table', { name: '五维评级热力矩阵' })).toBeVisible();

    await page.getByRole('button', { name: '分项评价' }).click();
    await expect(page.getByText('第四部分 · 分项评价')).toBeVisible();
    for (const dimension of report.dimensions) {
      await expectDimensionConsistency(page, dimension);
      await expect(page.getByTestId(`innovation-report-dimension-text-${dimension.key}`)).toContainText(
        scenarioPayload.dimensions[dimension.key].evidence,
      );
      await expect(page.getByTestId(`innovation-report-dimension-text-${dimension.key}`)).toContainText(
        scenarioPayload.dimensions[dimension.key].improvement_plan,
      );
    }

    await page.getByRole('button', { name: '综合评价与建议' }).click();
    await expect(page.getByText('第五部分 · 综合评价与建议')).toBeVisible();
    await expect(page.getByTestId('innovation-report-formula')).toContainText(report.formula);
    await expect(page.getByTestId('innovation-report-summary-score')).toContainText(String(report.total_score));
    await expect(page.getByTestId('innovation-report-summary-grade')).toContainText(report.grade_label);
    await expect(page.getByTestId('innovation-report-disclaimer')).toContainText(report.disclaimer);

    const detailResponse = await page.request.get(`/api/normative/innovation-assessments/${report.id}`);
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();
    expect(detail.dimensions).toEqual(report.dimensions);
    expect(detail.total_score).toBe(report.total_score);

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /下载 JSON|下载 UTF-8 JSON/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`innovation-report-${report.id}.json`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded innovation JSON report file path was not available');
    }
    const payload = JSON.parse(await readFile(downloadPath, 'utf8'));
    expect(payload.id).toBe(report.id);
    expect(payload.thesis_title).toBe(scenarioPayload.thesis_title);
    expect(payload.total_score).toBe(report.total_score);
    expect(payload.grade_label).toBe(report.grade_label);
    expect(payload.formula).toBe(report.formula);
    expect(payload.dimensions).toEqual(report.dimensions);
    expect(payload.scoring_snapshot.dimensions).toEqual(report.dimensions);

    await expect(page.getByRole('button', { name: '浏览器打印' })).toBeVisible();
  });
});
