const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-DUPLICATION-DETECT';
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

async function createCorpusSampleForScenario(page, title, content) {
  const response = await page.request.post('/api/normative/duplication-corpus', {
    data: {
      title,
      subject: '管理学',
      year: 2024,
      content,
      source_type: 'paste',
      source_filename: null,
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function clearCorpus(page) {
  const listResponse = await page.request.get('/api/normative/duplication-corpus');
  expect(listResponse.status()).toBe(200);
  const body = await listResponse.json();
  for (const sample of body.samples) {
    const deleteResponse = await page.request.delete(`/api/normative/duplication-corpus/${sample.id}`);
    expect(deleteResponse.status()).toBe(204);
  }
}

test.describe('FEAT-DUPLICATION-DETECT local similarity detection scenarios', () => {
  test('FEAT-DUPLICATION-DETECT:SCENARIO:001 student detects a local sample match with Jaccard score, similar paragraph, and total similarity rate', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await clearCorpus(page);
    const sampleText = '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。平台建设需要兼顾数据共享、流程再造和持续评估。';
    await createCorpusSampleForScenario(page, `E2E 高校数字治理样本 ${Date.now()}`, sampleText);

    await loginAs(page, 'student01');
    await page.goto('/duplication-detect');

    await expect(page.getByText('文档上传')).toBeVisible();
    await page.getByPlaceholder(/粘贴待检测论文文本/).fill([
      '本文首先分析高校数字治理平台的建设背景。',
      '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
      '因此，本文认为相关单位应当进一步完善制度设计。',
    ].join('\n'));
    await page.getByRole('button', { name: '检测' }).click();

    await expect(page.getByText('检测已完成')).toBeVisible();
    await expect(page.getByText(/写作风险分为启发式风险提示，并非 AI 真伪结论/)).toBeVisible();
    await expect(page.getByText(/比对样本数：1/)).toBeVisible();
    await expect(page.getByText(/总相似率：[1-9]\d*%/)).toBeVisible();
    await expect(page.getByRole('heading', { name: /E2E 高校数字治理样本/ })).toBeVisible();
    await expect(page.getByText(/Jaccard：0\./)).toBeVisible();

    const apiResponse = await page.request.post('/api/normative/duplication-detections', {
      data: {
        text: '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
        source_type: 'paste',
      },
    });
    expect(apiResponse.status()).toBe(201);
    const apiBody = await apiResponse.json();
    expect(apiBody.status).toBe('completed');
    expect(apiBody.top_matches[0].segments[0].source_excerpt).toContain('高校数字治理平台的建设效果');
  });

  test('FEAT-DUPLICATION-DETECT:SCENARIO:002 student gets explicit no-sample similarity result while writing risk still completes', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await clearCorpus(page);

    await loginAs(page, 'student01');
    await page.goto('/duplication-detect');

    await page.getByPlaceholder(/粘贴待检测论文文本/).fill([
      '首先，本文对相关问题进行分析。',
      '其次，本文对相关问题进行分析。',
      '综上所述，相关方面应当予以重视。',
    ].join('\n'));
    await page.getByRole('button', { name: '检测' }).click();

    await expect(page.getByText('检测已完成')).toBeVisible();
    await expect(page.getByText('无可用样本，未伪造比对结果。')).toBeVisible();
    await expect(page.getByText('比对样本数：0')).toBeVisible();
    await expect(page.getByText('总相似率：0%')).toBeVisible();
    await expect(page.getByText(/风险分：\d+/)).toBeVisible();
    await expect(page.getByText(/写作风险分为启发式风险提示，并非 AI 真伪结论/)).toBeVisible();

    const apiResponse = await page.request.post('/api/normative/duplication-detections', {
      data: {
        text: '无样本时也需要完成写作风险计算，不能伪造命中样本。',
        source_type: 'paste',
      },
    });
    expect(apiResponse.status()).toBe(201);
    const apiBody = await apiResponse.json();
    expect(apiBody).toMatchObject({
      status: 'no_samples',
      sample_count: 0,
      top_matches: [],
      total_similarity_rate: 0,
    });
    expect(apiBody.effective_character_count).toBeGreaterThan(0);
    expect(apiBody.risk.label).toBe('heuristic_only');
  });
});
