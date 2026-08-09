const { closeDb, getDbPath, initializeDatabase } = require('./init_db');
const { seedDatabase } = require('./seed_db');
const { withTransaction } = require('./db_runtime');

const DEMO_USER_IDS = ['student01', 'supervisor01', 'college_admin01', 'school_admin01'];
const QUALITY_STUDENTS = [
  {
    id: 'student01',
    collegeId: 'college01',
    supervisorId: 'supervisor01',
    thesisTitle: '高校数字治理质量评价体系研究',
    levels: [5, 4, 4, 3, 4],
    similarityRate: 0.18,
    reviewScore: 84,
    severityCounts: { high: 1, medium: 2, low: 2 },
  },
  {
    id: 'student02',
    collegeId: 'college01',
    supervisorId: 'supervisor01',
    thesisTitle: '面向智慧校园的教学质量监测方法研究',
    levels: [4, 4, 3, 4, 3],
    similarityRate: 0.24,
    reviewScore: 78,
    severityCounts: { high: 0, medium: 3, low: 4 },
  },
  {
    id: 'student03',
    collegeId: 'college01',
    supervisorId: 'supervisor02',
    thesisTitle: '生成式人工智能支持研究生写作的应用研究',
    levels: [5, 5, 4, 4, 4],
    similarityRate: 0.12,
    reviewScore: 91,
    severityCounts: { high: 0, medium: 1, low: 2 },
  },
  {
    id: 'student04',
    collegeId: 'college02',
    supervisorId: 'supervisor03',
    thesisTitle: '区域高校学位论文质量保障机制比较研究',
    levels: [3, 3, 4, 3, 4],
    similarityRate: 0.31,
    reviewScore: 72,
    severityCounts: { high: 1, medium: 3, low: 3 },
  },
];

const DIMENSION_META = [
  ['research_topic', '研究选题', 0.2],
  ['research_method', '研究方法', 0.2],
  ['research_content', '研究内容', 0.25],
  ['research_conclusion', '研究结论', 0.2],
  ['application_value', '应用价值', 0.15],
];

const DEMO_ORIGINAL_TEXT = [
  '摘要',
  '本文围绕高校数字治理背景下的学位论文质量保障展开研究，构建可解释的质量评价框架。',
  '关键词：学位论文；质量评价；数字治理',
  '引言',
  '现有质量保障流程存在数据分散、反馈周期较长和评价口径不一致等问题。',
  '研究方法',
  '研究综合采用文献分析、案例比较和半结构化访谈方法，对不同学院的论文质量管理流程进行归纳。',
  '研究结果',
  '结果表明，统一规则、过程反馈和分角色数据治理能够提升质量管理的透明度与可追溯性。',
  '结论',
  '本文提出的评价框架可为校内试点提供参考，但仍需在更大样本范围内持续验证。',
  '参考文献',
  '[1] 李明. 高校数字治理研究[J]. 教育信息化研究, 2025(3): 12-20.',
  '[2] 王芳. 学位论文质量保障机制研究[J]. 研究生教育, 2024(6): 44-50.',
].join('\n');

function isoDaysAgo(days, hour) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  date.setUTCHours(hour, 0, 0, 0);
  return date.toISOString();
}

function buildNormativeIssues() {
  return [
    {
      finding_id: 'finding-norm-001',
      rule_id: 'TEXT-LONG-SENTENCE',
      category: '文本质量',
      severity: 'medium',
      line: 5,
      column: 1,
      excerpt: '现有质量保障流程存在数据分散、反馈周期较长和评价口径不一致等问题。',
      message: '该句信息较集中，建议拆分后分别说明问题与影响。',
      suggestion: '将现状问题和造成的影响拆分为两个句子。',
    },
    {
      finding_id: 'finding-norm-002',
      rule_id: 'REFERENCE-CONSISTENCY',
      category: '参考文献',
      severity: 'low',
      line: 13,
      column: 1,
      excerpt: '[1] 李明. 高校数字治理研究[J].',
      message: '参考文献著录项建议统一空格和标点格式。',
      suggestion: '按当前学院发布的参考文献规则统一著录格式。',
    },
    {
      finding_id: 'finding-norm-003',
      rule_id: 'SECTION-COMPLETENESS',
      category: '章节顺序',
      severity: 'low',
      line: 1,
      column: 1,
      excerpt: '摘要',
      message: '章节结构完整，建议在摘要中进一步明确样本规模。',
      suggestion: '补充研究对象数量和数据时间范围。',
    },
  ];
}

function buildInnovationSnapshots(student, createdAt) {
  const dimensionsInput = {};
  const levels = {};
  const dimensions = DIMENSION_META.map(([key, label, weight], index) => {
    const level = student.levels[index];
    const rawScore = level * 20;
    levels[key] = level;
    dimensionsInput[key] = {
      level,
      evidence: `${label}证据来自论文正文、访谈材料和案例比较结果，能够对应主要结论并支持复核。`,
      improvement_plan: `${label}下一步将补充样本说明、数据来源和适用边界，使论证过程更加完整。`,
    };
    return {
      key,
      label,
      level,
      raw_score: rawScore,
      weight,
      weighted_score: Math.round(rawScore * weight * 10) / 10,
    };
  });
  const totalScore = dimensions.reduce((sum, item) => sum + item.weighted_score, 0);
  const gradeLabel = totalScore >= 85 ? '优秀' : totalScore >= 70 ? '良好' : totalScore >= 60 ? '一般' : '待提升';
  const inputSnapshot = {
    thesis_title: student.thesisTitle,
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '教育经济与管理',
    research_direction: '高校数字治理与质量保障',
    research_background: DEMO_ORIGINAL_TEXT,
    dimensions: dimensionsInput,
  };
  const scoringSnapshot = {
    degree_type: 'master',
    total_score: totalScore,
    grade_label: gradeLabel,
    formula: '各维度原始分 × 硕士论文维度权重后求和',
    dimensions,
    input: { degree_type: 'master', levels },
  };
  return { inputSnapshot, scoringSnapshot, createdAt };
}

function buildAiScoreItems(totalScore) {
  const meta = [
    ['section_completeness', '章节完整性'],
    ['reference_count', '参考文献数量'],
    ['normative_quality', '规范问题控制'],
    ['argument_structure', '论证结构'],
    ['language_quality', '语言表达'],
  ];
  const base = Math.floor(totalScore / meta.length);
  let remainder = totalScore - base * meta.length;
  return meta.map(([key, label]) => {
    const score = base + (remainder-- > 0 ? 1 : 0);
    return {
      key,
      label,
      points: 20,
      score,
      findings: score >= 18 ? [] : [`${label}仍有少量项目建议由导师结合正文确认`],
    };
  });
}

function buildDuplicationReport(student) {
  return {
    status: 'completed',
    source_type: 'file',
    source_filename: `[演示]${student.id}-相似度检测.txt`,
    threshold: 0.3,
    effective_character_count: DEMO_ORIGINAL_TEXT.length,
    total_similarity_rate: student.similarityRate,
    sample_count: 3,
    top_matches: [
      {
        sample_id: 'demo-corpus-digital-governance',
        title: '高校数字治理与质量保障案例样本',
        subject: '教育管理',
        year: 2025,
        jaccard_score: student.similarityRate,
        matched_character_count: 42,
        segments: [
          {
            source_start: 28,
            source_end: 70,
            sample_start: 15,
            sample_end: 57,
            source_excerpt: '构建可解释的质量评价框架',
            sample_excerpt: '形成可解释、可追溯的质量评价框架',
          },
        ],
      },
    ],
    risk: {
      score: Math.round(student.similarityRate * 100),
      label: 'heuristic_only',
      explanation: '风险分仅依据本地样本相似片段和文本特征计算。',
      factors: {
        paragraph_duplication_rate: student.similarityRate,
        sentence_length_low_variation: 0.18,
        template_connector_density: 0.12,
        vague_phrase_density: 0.08,
      },
      weights: {
        paragraph_duplication_rate: 0.5,
        sentence_length_low_variation: 0.2,
        template_connector_density: 0.2,
        vague_phrase_density: 0.1,
      },
    },
  };
}

async function insertDemoRow(tx, summary, category, sql, params) {
  const result = await tx.run(sql, params);
  summary.inserted += result.changes;
  summary.by_category[category] = (summary.by_category[category] || 0) + result.changes;
}

async function seedHelperStudents(tx, summary) {
  for (const student of QUALITY_STUDENTS.slice(1)) {
    await insertDemoRow(
      tx,
      summary,
      'users',
      `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
       SELECT ?, ?, password_hash, 'STUDENT', ?, ?, 'COLLEGE'
         FROM auth_users
        WHERE username = 'student01'
       ON CONFLICT(username) DO NOTHING`,
      [student.id, student.id, student.collegeId, student.supervisorId],
    );
  }
}

async function seedCorpus(tx, summary) {
  const samples = [
    {
      id: 'demo-corpus-digital-governance',
      title: '高校数字治理与质量保障案例样本',
      subject: '教育管理',
      year: 2025,
      content:
        '高校数字治理需要形成可解释、可追溯的质量评价框架，通过统一规则、过程反馈和分角色数据治理提升管理透明度。',
    },
    {
      id: 'demo-corpus-graduate-writing',
      title: '研究生学术写作规范案例样本',
      subject: '研究生教育',
      year: 2024,
      content: '学术写作质量保障应覆盖章节结构、引文规范、论证逻辑和语言表达，并在导师指导下形成持续修改记录。',
    },
    {
      id: 'demo-corpus-ai-education',
      title: '生成式人工智能教育应用案例样本',
      subject: '教育技术',
      year: 2026,
      content: '生成式人工智能可辅助文本检查和过程反馈，但评价结果必须保持可解释性，并由教师对学术内容和结论负责。',
    },
  ];
  for (const [index, sample] of samples.entries()) {
    await insertDemoRow(
      tx,
      summary,
      'corpus',
      `INSERT OR IGNORE INTO duplication_corpus_samples (
         id, title, subject, year, content, source_type, source_filename, created_by, created_at
       ) VALUES (?, ?, ?, ?, ?, 'paste', NULL, 'school_admin01', ?)`,
      [sample.id, sample.title, sample.subject, sample.year, sample.content, isoDaysAgo(6 - index, 2 + index)],
    );
  }
}

async function seedQualityRecordSet(tx, summary, student, index) {
  const normativeCreatedAt = isoDaysAgo(3 - Math.min(index, 3), 2);
  const duplicationCreatedAt = isoDaysAgo(3 - Math.min(index, 3), 3);
  const innovationCreatedAt = isoDaysAgo(2 - Math.min(index, 2), 4);
  const reviewCreatedAt = isoDaysAgo(1 - Math.min(index, 1), 5);
  const normativeIssues = buildNormativeIssues();
  const duplicationReport = buildDuplicationReport(student);
  const { inputSnapshot, scoringSnapshot } = buildInnovationSnapshots(student, innovationCreatedAt);
  const aiScoreItems = buildAiScoreItems(student.reviewScore);

  await insertDemoRow(
    tx,
    summary,
    'normative',
    `INSERT OR IGNORE INTO normative_detection_tasks (
       id, user_id, status, source_type, source_filename, original_text,
       rule_snapshot_json, issues_json, severity_counts_json, created_at
     ) VALUES (?, ?, 'completed', 'file', ?, ?, ?, ?, ?, ?)`,
    [
      `demo-normative-${student.id}`,
      student.id,
      `[演示]${student.id}-规范性检测.txt`,
      DEMO_ORIGINAL_TEXT,
      JSON.stringify([
        {
          rule_id: 'TEXT-LONG-SENTENCE',
          title: '长句可读性检查',
          severity: 'medium',
        },
        {
          rule_id: 'REFERENCE-CONSISTENCY',
          title: '参考文献格式一致性',
          severity: 'low',
        },
        {
          rule_id: 'SECTION-COMPLETENESS',
          title: '章节完整性检查',
          severity: 'low',
        },
      ]),
      JSON.stringify(normativeIssues),
      JSON.stringify(student.severityCounts),
      normativeCreatedAt,
    ],
  );

  await insertDemoRow(
    tx,
    summary,
    'duplication',
    `INSERT OR IGNORE INTO duplication_detection_reports (
       id, user_id, source_type, source_filename, original_text, total_similarity_rate,
       writing_risk_score, sample_count, report_json, created_at
     ) VALUES (?, ?, 'file', ?, ?, ?, ?, 3, ?, ?)`,
    [
      `demo-duplication-${student.id}`,
      student.id,
      `[演示]${student.id}-相似度检测.txt`,
      DEMO_ORIGINAL_TEXT,
      student.similarityRate,
      Math.round(student.similarityRate * 100 + 16),
      JSON.stringify(duplicationReport),
      duplicationCreatedAt,
    ],
  );

  await insertDemoRow(
    tx,
    summary,
    'innovation',
    `INSERT OR IGNORE INTO innovation_assessment_snapshots (
       id, user_id, thesis_title, degree_type, primary_discipline, secondary_discipline,
       research_direction, input_snapshot_json, scoring_snapshot_json, created_at
     ) VALUES (?, ?, ?, 'master', '管理学', '教育经济与管理', '高校数字治理与质量保障', ?, ?, ?)`,
    [
      `demo-innovation-${student.id}`,
      student.id,
      student.thesisTitle,
      JSON.stringify(inputSnapshot),
      JSON.stringify(scoringSnapshot),
      innovationCreatedAt,
    ],
  );

  await insertDemoRow(
    tx,
    summary,
    'ai_review',
    `INSERT OR IGNORE INTO ai_review_runs (
       id, user_id, thesis_title, template_id, source_type, source_filename, original_text,
       section_snapshot_json, reference_count, character_count, normative_issues_json,
       score_items_json, total_score, result_label, missing_sections_json, rubric_snapshot_json, created_at
     ) VALUES (?, ?, ?, 'academic_master', 'file', ?, ?, ?, 12, ?, ?, ?, ?, ?, '[]', ?, ?)`,
    [
      `demo-ai-review-${student.id}`,
      student.id,
      student.thesisTitle,
      `[演示]${student.id}-辅助评阅.txt`,
      DEMO_ORIGINAL_TEXT,
      JSON.stringify([
        { name: '摘要', present: true },
        { name: '关键词', present: true },
        { name: '引言', present: true },
        { name: '研究方法', present: true },
        { name: '结论', present: true },
        { name: '参考文献', present: true },
      ]),
      DEMO_ORIGINAL_TEXT.length,
      JSON.stringify(normativeIssues.slice(0, 2)),
      JSON.stringify(aiScoreItems),
      student.reviewScore,
      student.reviewScore >= 80 ? '基础检查通过' : '建议修改后复核',
      JSON.stringify({
        templates: [{ template_id: 'academic_master', name: '学术型硕士' }],
        passing_rule: {
          minimum_objective_score: 80,
          no_required_section_missing: true,
        },
      }),
      reviewCreatedAt,
    ],
  );
}

async function seedRoleHistory(tx, summary, userId, index) {
  const student = {
    id: userId,
    thesisTitle: `${userId} 演示论文质量评阅记录`,
    levels: [5, 4, 4, 3, 4],
    similarityRate: 0.21 + index * 0.02,
    reviewScore: 82 - index,
    severityCounts: { high: 0, medium: 2, low: 3 },
  };
  await seedQualityRecordSet(tx, summary, student, index);
}

async function seedPolishHistory(tx, summary, userId, index) {
  const wholeOriginal = '本研究研究围绕高校质量保障展开！！  现有流程存在重复重复表达，需要进一步优化。';
  const wholePolished = '本研究围绕高校质量保障展开！现有流程存在重复表达，需要进一步优化。';
  const wholeChanges = [
    {
      original_text: '研究研究',
      new_text: '研究',
      position: 3,
      rule: '重复词优化',
      reason: '删除连续重复词',
    },
    {
      original_text: '！！  ',
      new_text: '！',
      position: 17,
      rule: '标点与空格规范',
      reason: '合并重复标点和多余空格',
    },
    {
      original_text: '重复重复',
      new_text: '重复',
      position: 31,
      rule: '重复词优化',
      reason: '删除连续重复词',
    },
  ];
  await insertDemoRow(
    tx,
    summary,
    'whole_polish',
    `INSERT OR IGNORE INTO whole_polish_results (
       id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json, created_at
     ) VALUES (?, ?, 'file', ?, ?, ?, 'standard', ?, ?)`,
    [
      `demo-whole-polish-${userId}`,
      userId,
      `[演示]${userId}-全文润色.txt`,
      wholeOriginal,
      wholePolished,
      JSON.stringify(wholeChanges),
      isoDaysAgo(2, 7 + index),
    ],
  );

  const localOriginal = '该结论能够有效有效提升管理效率。。';
  const localPolished = '该结论能够有效提升管理效率。';
  await insertDemoRow(
    tx,
    summary,
    'local_polish',
    `INSERT OR IGNORE INTO local_polish_results (
       id, user_id, original_text, polished_text, level, rule_version, changes_json,
       diff_segments_json, source_result_id, retry_of, created_at
     ) VALUES (?, ?, ?, ?, 'standard', 'local-polish-rules-v1', ?, ?, NULL, NULL, ?)`,
    [
      `demo-local-polish-${userId}`,
      userId,
      localOriginal,
      localPolished,
      JSON.stringify([
        {
          original_text: '有效有效',
          new_text: '有效',
          position: 6,
          rule: '重复词优化',
        },
        {
          original_text: '。。',
          new_text: '。',
          position: 17,
          rule: '重复标点优化',
        },
      ]),
      JSON.stringify([
        { type: 'unchanged', text: '该结论能够', position: 0 },
        {
          type: 'replacement',
          original_text: '有效有效',
          new_text: '有效',
          text: '有效',
          position: 6,
          rule: '重复词优化',
        },
        { type: 'unchanged', text: '提升管理效率', position: 10 },
        {
          type: 'replacement',
          original_text: '。。',
          new_text: '。',
          text: '。',
          position: 16,
          rule: '重复标点优化',
        },
      ]),
      isoDaysAgo(1, 7 + index),
    ],
  );
}

async function seedReviewWorkflow(tx, summary) {
  const reportId = 'demo-normative-student01';
  const submissions = [
    {
      id: 'demo-submission-pending',
      batchId: 'demo-batch-round-3',
      status: 'submitted_pending_review',
      todoStatus: 'pending',
      title: '《高校数字治理质量评价体系研究》第三轮待批阅',
      createdAt: isoDaysAgo(0, 8),
    },
    {
      id: 'demo-submission-feedback',
      batchId: 'demo-batch-round-2',
      status: 'review_completed_feedback',
      todoStatus: 'done',
      title: '《高校数字治理质量评价体系研究》第二轮批阅',
      createdAt: isoDaysAgo(2, 8),
      feedback: {
        id: 'demo-feedback-round-2',
        lockedAt: isoDaysAgo(1, 3),
        annotations: [
          {
            finding_id: 'finding-norm-001',
            comment: '建议拆分长句，并补充流程问题对研究结论的具体影响。',
          },
          {
            finding_id: 'finding-norm-002',
            comment: '请统一两条参考文献的标点、卷期和页码格式。',
          },
        ],
        overallEvaluation: '论文结构完整，研究问题明确，已具备进一步完善和送审的基础。',
        improvementSuggestions: '重点补充样本来源说明，统一参考文献格式，并在结论中明确研究适用边界。',
      },
    },
    {
      id: 'demo-submission-viewed',
      batchId: 'demo-batch-round-1',
      status: 'student_viewed_feedback',
      todoStatus: 'done',
      title: '《高校数字治理质量评价体系研究》第一轮批阅',
      createdAt: isoDaysAgo(5, 8),
      feedback: {
        id: 'demo-feedback-round-1',
        lockedAt: isoDaysAgo(4, 3),
        annotations: [
          {
            finding_id: 'finding-norm-003',
            comment: '摘要建议增加研究样本数量和访谈对象范围。',
          },
        ],
        overallEvaluation: '选题具有现实意义，初稿已形成基本框架，但方法说明仍需补充。',
        improvementSuggestions: '补充研究设计、样本选择依据和数据处理步骤后再提交下一轮。',
      },
    },
  ];

  for (const item of submissions) {
    await insertDemoRow(
      tx,
      summary,
      'submissions',
      `INSERT OR IGNORE INTO report_submissions (
         id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at
       ) VALUES (?, ?, 'student01', 'supervisor01', 'normative', ?, ?, ?)`,
      [item.id, item.batchId, reportId, item.status, item.createdAt],
    );
    await insertDemoRow(
      tx,
      summary,
      'todos',
      `INSERT OR IGNORE INTO in_app_todos (
         id, submission_id, assignee_id, actor_id, status, title, created_at
       ) VALUES (?, ?, 'supervisor01', 'student01', ?, ?, ?)`,
      [`demo-todo-${item.id}`, item.id, item.todoStatus, item.title, item.createdAt],
    );
    if (item.feedback) {
      await insertDemoRow(
        tx,
        summary,
        'feedback',
        `INSERT OR IGNORE INTO supervisor_review_feedback (
           id, submission_id, supervisor_id, annotations_json, overall_evaluation,
           improvement_suggestions, locked_at, created_at
         ) VALUES (?, ?, 'supervisor01', ?, ?, ?, ?, ?)`,
        [
          item.feedback.id,
          item.id,
          JSON.stringify(item.feedback.annotations),
          item.feedback.overallEvaluation,
          item.feedback.improvementSuggestions,
          item.feedback.lockedAt,
          item.feedback.lockedAt,
        ],
      );
    }
  }
}

async function seedDemoDatabase(options = {}) {
  if (options.confirmDemoData !== true) {
    throw new Error('演示数据初始化需要显式传入 confirmDemoData: true');
  }

  await seedDatabase();
  return withTransaction(async (tx) => {
    const summary = { inserted: 0, by_category: {} };
    await seedHelperStudents(tx, summary);
    await seedCorpus(tx, summary);

    for (const [index, student] of QUALITY_STUDENTS.entries()) {
      await seedQualityRecordSet(tx, summary, student, index);
    }
    for (const [index, userId] of DEMO_USER_IDS.entries()) {
      if (userId !== 'student01') {
        await seedRoleHistory(tx, summary, userId, index);
      }
      await seedPolishHistory(tx, summary, userId, index);
    }
    await seedReviewWorkflow(tx, summary);

    const totals = {};
    for (const [label, table] of Object.entries({
      users: 'auth_users',
      normative: 'normative_detection_tasks',
      duplication: 'duplication_detection_reports',
      innovation: 'innovation_assessment_snapshots',
      ai_review: 'ai_review_runs',
      whole_polish: 'whole_polish_results',
      local_polish: 'local_polish_results',
      corpus: 'duplication_corpus_samples',
      submissions: 'report_submissions',
      todos: 'in_app_todos',
      feedback: 'supervisor_review_feedback',
    })) {
      const row = await tx.get(`SELECT COUNT(*) AS count FROM ${table}`);
      totals[label] = Number(row?.count || 0);
    }
    return { ...summary, totals };
  });
}

async function runFromCli() {
  const explicitDbPath = process.env.ARC_DB_FILE || process.env.DATABASE_FILE;
  if (!explicitDbPath) {
    throw new Error('拒绝初始化演示数据：请显式设置 ARC_DB_FILE 或 DATABASE_FILE');
  }
  if (process.env.ARC_ALLOW_DEMO_SEED !== '1') {
    throw new Error('拒绝初始化演示数据：请显式设置 ARC_ALLOW_DEMO_SEED=1');
  }

  await initializeDatabase({ dbPath: explicitDbPath });
  const summary = await seedDemoDatabase({ confirmDemoData: true });
  console.log(JSON.stringify({ database: getDbPath(), ...summary }, null, 2));
}

if (require.main === module) {
  runFromCli()
    .then(() => closeDb())
    .catch(async (error) => {
      console.error(`Demo database seed failed: ${error.message}`);
      await closeDb().catch(() => undefined);
      process.exitCode = 1;
    });
}

module.exports = {
  DEMO_USER_IDS,
  QUALITY_STUDENTS,
  seedDemoDatabase,
};
