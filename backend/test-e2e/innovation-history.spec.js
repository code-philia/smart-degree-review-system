const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-INNOVATION-HISTORY';
void reqId;

const demoPassword = 'ArcDemo123!';

function longText(label) {
  return `${label}证据围绕论文创新性评估展开，包含可核验资料和论证依据，超过二十个字符。`;
}

function assessmentPayload(thesisTitle, degreeType, levels) {
  return {
    thesis_title: thesisTitle,
    degree_type: degreeType,
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    dimensions: {
      research_topic: {
        level: levels.research_topic,
        evidence: longText('研究选题'),
        improvement_plan: '研究选题改进计划将补充前沿文献和政策场景，增强问题意识。',
      },
      research_method: {
        level: levels.research_method,
        evidence: longText('研究方法'),
        improvement_plan: '研究方法改进计划将增加访谈样本和三角验证，提升方法可靠性。',
      },
      research_content: {
        level: levels.research_content,
        evidence: longText('研究内容'),
        improvement_plan: '研究内容改进计划将扩展案例比较和数据解释，增强论证深度。',
      },
      research_conclusion: {
        level: levels.research_conclusion,
        evidence: longText('研究结论'),
        improvement_plan: '研究结论改进计划将明确适用边界和进一步研究方向，减少泛化。',
      },
      application_value: {
        level: levels.application_value,
        evidence: longText('应用价值'),
        improvement_plan: '应用价值改进计划将设计落地指标和推广条件，提升实践可用性。',
      },
    },
  };
}

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function createAssessment(page, payload) {
  const response = await page.request.post('/api/normative/innovation-assessments', { data: payload });
  expect(response.status()).toBe(201);
  const report = await response.json();
  expect(report.id).toEqual(expect.any(String));
  expect(report.thesis_title).toBe(payload.thesis_title);
  return report;
}

test.describe('FEAT-INNOVATION-HISTORY student history scenario', () => {
  test('FEAT-INNOVATION-HISTORY:SCENARIO:001 student opens history, sees only own assessments newest first, and enters the corresponding report', async ({ page }) => {
    await loginAs(page, 'supervisor01');
    const hiddenSupervisorReport = await createAssessment(
      page,
      assessmentPayload(`supervisor-hidden-innovation-${Date.now()}`, 'master', {
        research_topic: 5,
        research_method: 4,
        research_content: 4,
        research_conclusion: 3,
        application_value: 4,
      }),
    );

    await loginAs(page, 'student01');
    const olderReport = await createAssessment(
      page,
      assessmentPayload(`student01-innovation-old-${Date.now()}`, 'master', {
        research_topic: 4,
        research_method: 3,
        research_content: 4,
        research_conclusion: 3,
        application_value: 3,
      }),
    );
    const newerReport = await createAssessment(
      page,
      assessmentPayload(`student01-innovation-new-${Date.now()}`, 'doctoral', {
        research_topic: 5,
        research_method: 5,
        research_content: 4,
        research_conclusion: 4,
        application_value: 5,
      }),
    );

    await page.goto('/innovation-history');
    await expect(page.getByRole('heading', { name: '创新性分析历史记录' })).toBeVisible();
    await expect(page.getByText(/共 \d+ 条记录/)).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '论文题目' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '学历层次' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '综合分' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '等级' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '生成时间' })).toBeVisible();

    const rows = page.getByRole('row');
    const newerRow = rows.filter({ hasText: newerReport.thesis_title });
    const olderRow = rows.filter({ hasText: olderReport.thesis_title });
    await expect(newerRow).toBeVisible();
    await expect(olderRow).toBeVisible();
    await expect(page.getByText(hiddenSupervisorReport.thesis_title)).toHaveCount(0);
    await expect(newerRow).toContainText('博士');
    await expect(olderRow).toContainText('硕士');
    await expect(newerRow).toContainText(String(newerReport.total_score));
    await expect(newerRow).toContainText(newerReport.grade_label);
    await expect(olderRow).toContainText(String(olderReport.total_score));
    await expect(olderRow).toContainText(olderReport.grade_label);

    const newerBox = await newerRow.boundingBox();
    const olderBox = await olderRow.boundingBox();
    expect(newerBox).not.toBeNull();
    expect(olderBox).not.toBeNull();
    expect(newerBox.y).toBeLessThan(olderBox.y);

    await page.getByPlaceholder('请输入论文题目搜索').fill('innovation-new');
    await page.getByRole('button', { name: '搜索' }).click();
    await expect(newerRow).toBeVisible();
    await expect(olderRow).toHaveCount(0);

    await newerRow.getByRole('link', { name: '报告预览' }).click();
    await expect(page).toHaveURL(new RegExp(`/innovation-assessments/${newerReport.id}$`));
    await expect(page.getByRole('heading', { name: '学位论文创新性分析报告' })).toBeVisible();
    await expect(page.getByTestId('innovation-report-basic-info')).toContainText(newerReport.thesis_title);
    await expect(page.getByTestId('innovation-report-total-score')).toContainText(String(newerReport.total_score));
    await expect(page.getByTestId('innovation-report-grade')).toContainText(newerReport.grade_label);

    const historyResponse = await page.request.get('/api/normative/innovation-assessments');
    expect(historyResponse.status()).toBe(200);
    const history = await historyResponse.json();
    expect(history.records.map((record) => record.id)).toContain(newerReport.id);
    expect(history.records.map((record) => record.id)).not.toContain(hiddenSupervisorReport.id);
  });
});
