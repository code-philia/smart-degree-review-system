import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, run } = require('../src/database');
const { createCorpusSample } = require('../src/normative/duplicationCorpusRepository');
const {
  DEFAULT_DUPLICATION_MATCH_THRESHOLD,
  runDuplicationDetection,
} = require('../src/normative/duplicationDetectionService');

const REQ_ID = 'FEAT-DUPLICATION-DETECT';
void REQ_ID;

let harness;

const student = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
};

function sample(index, content, overrides = {}) {
  return createCorpusSample({
    id: `service-sample-${index}`,
    title: `样本 ${index}`,
    subject: '计算机科学',
    year: 2024,
    content,
    source_type: 'paste',
    source_filename: null,
    created_by: 'school_admin01',
    created_at: `2024-01-0${index}T00:00:00.000Z`,
    ...overrides,
  });
}

function factorContribution(factors, weights) {
  return Object.entries(weights).reduce((total, [key, weight]) => total + factors[key] * weight, 0);
}

describe('FEAT-DUPLICATION-DETECT service similarity and risk rules', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-duplication-detect-service', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM duplication_corpus_samples');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-DUPLICATION-DETECT:FUNC:SIMILARITY:001 lowercases text, normalizes whitespace, removes punctuation, and scores character 5-gram Jaccard matches', async () => {
    await sample(1, 'alpha beta gamma delta epsilon');
    await sample(2, 'completely unrelated corpus text');

    const result = await runDuplicationDetection(student, {
      text: 'ALPHA,   beta!! gamma; delta epsilon.',
      source_type: 'paste',
    });

    expect(result.status).toBe('completed');
    expect(result.threshold).toBe(DEFAULT_DUPLICATION_MATCH_THRESHOLD);
    expect(result.effective_character_count).toBeGreaterThan(0);
    expect(result.top_matches[0]).toMatchObject({
      sample_id: 'service-sample-1',
      title: '样本 1',
      jaccard_score: 1,
    });
    expect(result.top_matches).toHaveLength(1);
  });

  it('FEAT-DUPLICATION-DETECT:FUNC:RANKING:001 returns only the highest five threshold-matching samples in descending Jaccard order', async () => {
    const sourceText = '本研究采用问卷调查与访谈相结合的方法分析平台建设效果';
    await sample(1, `${sourceText}并提出治理建议`);
    await sample(2, `${sourceText}并开展案例比较`);
    await sample(3, `${sourceText}并形成评价指标`);
    await sample(4, `${sourceText}并总结实践路径`);
    await sample(5, `${sourceText}并说明数据来源`);
    await sample(6, `${sourceText}并讨论风险控制`);
    await sample(7, '完全不同的本地样本文本不会达到阈值');

    const result = await runDuplicationDetection(student, {
      text: sourceText,
      source_type: 'paste',
      threshold: 0.3,
    });

    expect(result.top_matches).toHaveLength(5);
    expect(result.top_matches.map((match) => match.sample_id)).not.toContain('service-sample-7');
    const scores = result.top_matches.map((match) => match.jaccard_score);
    expect(scores).toEqual([...scores].sort((left, right) => right - left));
    scores.forEach((score) => expect(score).toBeGreaterThanOrEqual(0.3));
  });

  it('FEAT-DUPLICATION-DETECT:FUNC:SEGMENTS:001 reports similar paragraph spans and de-duplicates overlapping matched source characters for total similarity rate', async () => {
    const repeatedParagraph = '高校数字治理平台需要统一数据标准并完善流程协同机制';
    await sample(1, `${repeatedParagraph}，同时加强质量评估。`);
    await sample(2, `${repeatedParagraph}，并推动跨部门协作。`);

    const result = await runDuplicationDetection(student, {
      text: `${repeatedParagraph}\n${repeatedParagraph}\n补充说明`,
      source_type: 'paste',
      threshold: 0.25,
    });

    expect(result.top_matches.length).toBeGreaterThan(0);
    for (const match of result.top_matches) {
      expect(match.segments.length).toBeGreaterThan(0);
      for (const segment of match.segments) {
        expect(segment.source_start).toBeGreaterThanOrEqual(0);
        expect(segment.source_end).toBeGreaterThan(segment.source_start);
        expect(segment.sample_end).toBeGreaterThan(segment.sample_start);
        expect(segment.source_excerpt).toContain('高校数字治理平台');
        expect(segment.sample_excerpt).toContain('高校数字治理平台');
      }
    }
    expect(result.total_similarity_rate).toBeGreaterThan(0);
    expect(result.total_similarity_rate).toBeLessThanOrEqual(1);
  });

  it('FEAT-DUPLICATION-DETECT:FUNC:RISK:001 calculates weighted heuristic writing risk without presenting an AI authenticity conclusion', async () => {
    const repetitiveText = [
      '首先，本文对相关问题进行分析。',
      '首先，本文对相关问题进行分析。',
      '首先，本文对相关问题进行分析。',
      '综上所述，具有重要意义，相关方面应予以重视。',
    ].join('\n');

    const result = await runDuplicationDetection(student, {
      text: repetitiveText,
      source_type: 'paste',
    });

    expect(result.status).toBe('no_samples');
    expect(result.risk).toMatchObject({
      label: 'heuristic_only',
      explanation: expect.stringMatching(/启发式风险|并非 AI 真伪结论/),
      weights: {
        paragraph_duplication_rate: 0.35,
        sentence_length_low_variation: 0.25,
        template_connector_density: 0.2,
        vague_phrase_density: 0.2,
      },
    });
    expect(result.risk.factors.paragraph_duplication_rate).toBeGreaterThan(0);
    expect(result.risk.factors.template_connector_density).toBeGreaterThan(0);
    expect(result.risk.factors.vague_phrase_density).toBeGreaterThan(0);
    expect(result.risk.score).toBeCloseTo(factorContribution(result.risk.factors, result.risk.weights), 5);
  });

  it('FEAT-DUPLICATION-DETECT:TYPE:001 runs AIGC writing-risk mode independently from the corpus and labels the result honestly', async () => {
    const result = await runDuplicationDetection(student, {
      text: '首先，本文从多个方面进行分析。因此，相关问题具有重要意义。',
      source_type: 'paste',
      detection_type: 'aigc_writing_risk',
    });

    expect(result).toMatchObject({
      status: 'completed',
      detection_type: 'aigc_writing_risk',
      detection_type_label: 'AIGC 写作风险检测',
      sample_count: 0,
      top_matches: [],
      risk: {
        label: 'heuristic_only',
        explanation: expect.stringMatching(/并非 AI 真伪结论/),
      },
    });
  });

  it('FEAT-DUPLICATION-DETECT:FUNC:VALIDATION:001 rejects missing, unsupported-role, blank, and oversized detection requests before corpus reads are needed', async () => {
    await expect(runDuplicationDetection(null, { text: '有效文本' })).rejects.toMatchObject({ status: 401 });
    await expect(runDuplicationDetection({ ...student, role: 'GUEST' }, { text: '有效文本' })).rejects.toMatchObject({ status: 403 });
    await expect(runDuplicationDetection(student, { text: '   ' })).rejects.toMatchObject({ status: 400 });
    await expect(runDuplicationDetection(student, { text: 'a'.repeat(50 * 1024 * 1024 + 1) })).rejects.toMatchObject({ status: 413 });
  });
});
