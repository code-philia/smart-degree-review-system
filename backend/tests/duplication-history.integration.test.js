import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createCorpusSample } = require('../src/normative/duplicationCorpusRepository');
const {
  createDuplicationHistoryRecord,
  findDuplicationHistoryByIdForUser,
  listDuplicationHistoryByUser,
} = require('../src/normative/duplicationHistoryRepository');
const {
  buildDuplicationDownloadPayload,
  createDuplicationHistoryFromDetection,
  getDuplicationReportForUser,
  listDuplicationHistoryForUser,
} = require('../src/normative/duplicationHistoryService');

const REQ_ID = 'FEAT-DUPLICATION-HISTORY';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

function cookieValue(response) {
  return response.headers['set-cookie']?.find((cookie) => cookie.startsWith('arc_session='));
}

async function login(username) {
  const response = await request(app)
    .post('/api/auth/login')
    .send({ username, password: demoPassword })
    .expect(200);
  return cookieValue(response);
}

function detectionText(suffix = '') {
  return [
    '本文首先分析高校数字治理平台的建设背景。',
    '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
    `因此，本文认为相关单位应当进一步完善制度设计，提升协同治理能力。${suffix}`,
  ].join('\n');
}

function reportJson(overrides = {}) {
  return {
    status: 'completed',
    threshold: 0.65,
    total_similarity_rate: 0.42,
    sample_count: 3,
    risk: {
      label: 'heuristic_only',
      score: 71,
      explanation: '写作风险分为启发式风险提示，并非 AI 真伪结论。',
    },
    top_matches: [
      {
        sample_id: 'sample-001',
        title: '高校数字治理样本',
        jaccard_score: 0.72,
        segments: [
          {
            source_excerpt: '高校数字治理平台的建设效果',
            sample_excerpt: '高校数字治理平台的建设效果',
          },
        ],
      },
    ],
    ...overrides,
  };
}

async function seedHistoryRecord(overrides = {}) {
  return createDuplicationHistoryRecord({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    source_type: overrides.source_type || 'file',
    source_filename: overrides.source_filename || 'student01-查重报告.txt',
    original_text: overrides.original_text || detectionText(),
    total_similarity_rate: overrides.total_similarity_rate ?? 0.42,
    writing_risk_score: overrides.writing_risk_score ?? 71,
    sample_count: overrides.sample_count ?? 3,
    report_json: overrides.report_json || reportJson(),
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  });
}

async function seedMatchingCorpusSample() {
  return createCorpusSample({
    id: 'dup-history-sample-001',
    title: '查重历史样本',
    subject: '管理学',
    year: 2024,
    content: [
      '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
      '平台建设需要兼顾数据共享、流程再造和持续评估。',
    ].join('\n'),
    source_type: 'paste',
    source_filename: null,
    created_by: 'school_admin01',
    created_at: '2024-01-01T00:00:00.000Z',
  });
}

describe('FEAT-DUPLICATION-HISTORY owned history API, service, and persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-duplication-history', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-DUPLICATION-HISTORY:API:AUTHZ:001 denies anonymous history, detail, and JSON download before returning report data', async () => {
    const ownedReport = await seedHistoryRecord({ id: 'dup-history-anonymous-boundary' });

    await request(app).get('/api/normative/duplication-detection-reports').expect(401);
    await request(app).get(`/api/normative/duplication-detection-reports/${ownedReport.id}`).expect(401);
    await request(app).get(`/api/normative/duplication-detection-reports/${ownedReport.id}/download`).expect(401);
  });

  it('FEAT-DUPLICATION-HISTORY:SCENARIO:001 lists only student01 records in detection-time descending order and opens the owned report', async () => {
    await seedHistoryRecord({
      id: 'student01-history-old',
      source_filename: 'student01-第一次检测.txt',
      total_similarity_rate: 0.18,
      writing_risk_score: 43,
      sample_count: 2,
      created_at: '2026-08-04T09:00:00.000Z',
    });
    await seedHistoryRecord({
      id: 'student01-history-new',
      source_filename: 'student01-第二次检测.txt',
      total_similarity_rate: 0.37,
      writing_risk_score: 66,
      sample_count: 4,
      created_at: '2026-08-04T11:00:00.000Z',
    });
    await seedHistoryRecord({
      id: 'supervisor-history-hidden',
      user_id: 'supervisor01',
      source_filename: 'supervisor-不可见检测.txt',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    const cookie = await login('student01');

    await request(app)
      .get('/api/normative/duplication-detection-reports')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.records.map((record) => record.id)).toEqual(
          expect.arrayContaining(['student01-history-new', 'student01-history-old']),
        );
        expect(body.records.find((record) => record.id === 'supervisor-history-hidden')).toBeUndefined();
        const newIndex = body.records.findIndex((record) => record.id === 'student01-history-new');
        const oldIndex = body.records.findIndex((record) => record.id === 'student01-history-old');
        expect(newIndex).toBeGreaterThanOrEqual(0);
        expect(oldIndex).toBeGreaterThanOrEqual(0);
        expect(newIndex).toBeLessThan(oldIndex);
        expect(body.records[newIndex]).toMatchObject({
          source_filename: 'student01-第二次检测.txt',
          total_similarity_rate: 0.37,
          writing_risk_score: 66,
          sample_count: 4,
          created_at: '2026-08-04T11:00:00.000Z',
        });
      });

    await request(app)
      .get('/api/normative/duplication-detection-reports/student01-history-new')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body).toMatchObject({
          id: 'student01-history-new',
          user_id: 'student01',
          source_filename: 'student01-第二次检测.txt',
          total_similarity_rate: 0.37,
          writing_risk_score: 66,
          sample_count: 4,
        });
        expect(body.report_json).toMatchObject({ status: 'completed', risk: { label: 'heuristic_only' } });
      });
  });

  it('FEAT-DUPLICATION-HISTORY:API:DOWNLOAD:001 returns 404 for another user report and exports complete UTF-8 JSON attachment for the owner', async () => {
    const ownReport = await seedHistoryRecord({
      id: 'student01-download-history',
      source_filename: 'student01-下载报告.txt',
      original_text: '用于下载的原文',
      total_similarity_rate: 0.51,
      writing_risk_score: 82,
      sample_count: 5,
      report_json: reportJson({ total_similarity_rate: 0.51, sample_count: 5, risk: { label: 'heuristic_only', score: 82 } }),
    });
    const otherReport = await seedHistoryRecord({ id: 'supervisor-download-hidden', user_id: 'supervisor01' });
    const cookie = await login('student01');

    await request(app)
      .get(`/api/normative/duplication-detection-reports/${otherReport.id}`)
      .set('Cookie', cookie)
      .expect(404);

    await request(app)
      .get(`/api/normative/duplication-detection-reports/${ownReport.id}/download`)
      .set('Cookie', cookie)
      .expect(200)
      .expect('content-type', /application\/json; charset=utf-8/)
      .expect('content-disposition', new RegExp(`attachment; filename="duplication-report-${ownReport.id}\\.json"`))
      .expect(({ body }) => {
        expect(body).toMatchObject({
          id: ownReport.id,
          source_filename: 'student01-下载报告.txt',
          total_similarity_rate: 0.51,
          writing_risk_score: 82,
          sample_count: 5,
          original_text: '用于下载的原文',
        });
        expect(body.report_json).toMatchObject({ status: 'completed', risk: { score: 82 } });
      });
  });

  it('FEAT-DUPLICATION-HISTORY:FUNC:001 scopes service and repository reads by owner and shapes deterministic download payloads', async () => {
    const report = await seedHistoryRecord({ id: 'student01-service-history', created_at: '2026-08-04T13:00:00.000Z' });

    await expect(listDuplicationHistoryForUser(null)).rejects.toMatchObject({ status: 401 });
    await expect(getDuplicationReportForUser({ username: 'student01', role: 'UNSUPPORTED' }, report.id)).rejects.toMatchObject({ status: 403 });
    await expect(getDuplicationReportForUser({ username: 'student01', role: 'STUDENT' }, '')).rejects.toMatchObject({ status: 400 });
    await expect(getDuplicationReportForUser({ username: 'supervisor01', role: 'SUPERVISOR' }, report.id)).rejects.toMatchObject({ status: 404 });
    await expect(getDuplicationReportForUser({ username: 'student01', role: 'STUDENT' }, report.id)).resolves.toMatchObject({ id: report.id });
    await expect(findDuplicationHistoryByIdForUser(report.id, 'supervisor01')).resolves.toBeNull();
    await expect(listDuplicationHistoryByUser('student01')).resolves.toEqual(expect.arrayContaining([expect.objectContaining({ id: report.id })]));
    expect(buildDuplicationDownloadPayload(report)).toEqual({
      id: report.id,
      source_type: report.source_type,
      source_filename: report.source_filename,
      created_at: report.created_at,
      total_similarity_rate: report.total_similarity_rate,
      writing_risk_score: report.writing_risk_score,
      sample_count: report.sample_count,
      report_json: report.report_json,
      original_text: report.original_text,
    });
  });

  it('FEAT-DUPLICATION-HISTORY:API:PERSISTENCE:001 persists completed duplication detections into owner-scoped history without fabricated rows', async () => {
    await run('DELETE FROM duplication_detection_reports');
    await run('DELETE FROM duplication_corpus_samples');
    await seedMatchingCorpusSample();
    const cookie = await login('student01');

    const detectionResponse = await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .send({
        text: detectionText('第一次'),
        source_type: 'file',
        source_filename: 'student01-持久化检测.txt',
      })
      .expect(201);

    expect(detectionResponse.body.status).toBe('completed');

    await request(app)
      .get('/api/normative/duplication-detection-reports')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.records).toHaveLength(1);
        expect(body.records[0]).toMatchObject({
          user_id: 'student01',
          source_type: 'file',
          source_filename: 'student01-持久化检测.txt',
          total_similarity_rate: detectionResponse.body.total_similarity_rate,
          writing_risk_score: detectionResponse.body.risk.score,
          sample_count: detectionResponse.body.sample_count,
        });
        expect(body.records[0].report_json).toMatchObject({
          status: detectionResponse.body.status,
          total_similarity_rate: detectionResponse.body.total_similarity_rate,
          sample_count: detectionResponse.body.sample_count,
        });
      });

    await expect(createDuplicationHistoryFromDetection(
      { username: 'student01', role: 'STUDENT' },
      { text: '服务层原文', source_type: 'paste', source_filename: null },
      reportJson({ risk: { label: 'heuristic_only', score: 38 }, sample_count: 7, total_similarity_rate: 0.29 }),
    )).resolves.toMatchObject({
      user_id: 'student01',
      source_type: 'paste',
      source_filename: null,
      original_text: '服务层原文',
      total_similarity_rate: 0.29,
      writing_risk_score: 38,
      sample_count: 7,
    });
  });
});
