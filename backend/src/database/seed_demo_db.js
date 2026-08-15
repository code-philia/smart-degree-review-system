const { closeDb, getDbPath, initializeDatabase } = require('./init_db');
const { seedDatabase } = require('./seed_db');
const { withTransaction } = require('./db_runtime');

const DEMO_SEED_VERSION = '2026.08.15.2';
const DEMO_USER_IDS = ['student01', 'supervisor01', 'college_admin01', 'school_admin01'];
const SUPERVISOR_PROFILES = [
  { id: 'supervisor02', collegeId: 'college01' },
  { id: 'supervisor03', collegeId: 'college02' },
  { id: 'supervisor04', collegeId: 'college01' },
  { id: 'supervisor05', collegeId: 'college03' },
];
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
  {
    id: 'student05',
    collegeId: 'college01',
    supervisorId: 'supervisor01',
    thesisTitle: '专业学位研究生实践成果评价机制研究',
    levels: [4, 4, 4, 3, 5],
    similarityRate: 0.16,
    reviewScore: 86,
    severityCounts: { high: 0, medium: 2, low: 3 },
  },
  {
    id: 'student06',
    collegeId: 'college01',
    supervisorId: 'supervisor04',
    thesisTitle: '跨学科研究生培养质量影响因素研究',
    levels: [4, 5, 4, 4, 4],
    similarityRate: 0.2,
    reviewScore: 83,
    severityCounts: { high: 0, medium: 2, low: 4 },
  },
  {
    id: 'student07',
    collegeId: 'college02',
    supervisorId: 'supervisor03',
    thesisTitle: '科研诚信教育融入研究生培养全过程的路径研究',
    levels: [5, 4, 4, 4, 5],
    similarityRate: 0.14,
    reviewScore: 89,
    severityCounts: { high: 0, medium: 1, low: 3 },
  },
  {
    id: 'student08',
    collegeId: 'college03',
    supervisorId: 'supervisor05',
    thesisTitle: '学位论文预审环节风险识别与治理研究',
    levels: [4, 3, 4, 4, 4],
    similarityRate: 0.27,
    reviewScore: 76,
    severityCounts: { high: 1, medium: 2, low: 3 },
  },
];

const STUDENT_HISTORY_ROUNDS = [
  {
    key: 'proposal-revision',
    label: '开题后修订稿',
    daysAgo: 46,
    similarityRate: 0.29,
    reviewScore: 71,
    levels: [3, 3, 3, 3, 4],
    severityCounts: { high: 2, medium: 3, low: 3 },
  },
  {
    key: 'chapter-review',
    label: '章节送审稿',
    daysAgo: 31,
    similarityRate: 0.25,
    reviewScore: 76,
    levels: [4, 3, 4, 3, 4],
    severityCounts: { high: 1, medium: 3, low: 3 },
  },
  {
    key: 'midterm-revision',
    label: '中期检查修订稿',
    daysAgo: 20,
    similarityRate: 0.22,
    reviewScore: 80,
    levels: [4, 4, 4, 3, 4],
    severityCounts: { high: 1, medium: 2, low: 3 },
  },
  {
    key: 'pre-defense',
    label: '预答辩稿',
    daysAgo: 11,
    similarityRate: 0.19,
    reviewScore: 83,
    levels: [5, 4, 4, 3, 4],
    severityCounts: { high: 1, medium: 2, low: 2 },
  },
];

const DIMENSION_META = [
  ['research_topic', '研究选题', 0.2],
  ['research_method', '研究方法', 0.2],
  ['research_content', '研究内容', 0.25],
  ['research_conclusion', '研究结论', 0.2],
  ['application_value', '应用价值', 0.15],
];

const RESEARCH_CONTEXTS = [
  {
    primaryDiscipline: '管理学', secondaryDiscipline: '教育经济与管理', direction: '高校数字治理与质量保障',
    keywords: '研究生教育；质量保障；过程评价；数字治理',
    gap: '现有研究较多关注结果评价，对培养过程中的多主体协同、反馈时效及规则一致性讨论仍显不足。',
    method: '研究采用文献分析、案例比较和半结构化访谈方法，选取三所高校的培养管理实践作为案例，并对二十八名导师和研究生开展访谈。',
    finding: '研究发现，明确评价口径、建立分阶段反馈机制并保留修改证据，能够提升论文质量管理的透明度与可追溯性。',
    limitation: '样本范围和跨学科适用性仍需在后续研究中验证。',
    corpusIndex: 0,
  },
  {
    primaryDiscipline: '教育学', secondaryDiscipline: '教育技术学', direction: '智慧校园学习分析',
    keywords: '智慧校园；教学质量；学习分析；过程预警',
    gap: '既有教学质量监测多依赖期末结果，关于过程数据如何支持课程改进的证据仍不充分。',
    method: '研究结合平台日志分析、课程观察与教师访谈，对四门研究生课程的学习过程数据进行交叉验证。',
    finding: '持续呈现任务完成节奏和反馈响应情况，有助于教师更早识别学习支持需求并调整教学安排。',
    limitation: '不同课程的任务结构差异可能影响指标的可比性。',
    corpusIndex: 1,
  },
  {
    primaryDiscipline: '教育学', secondaryDiscipline: '高等教育学', direction: '生成式人工智能与学术写作',
    keywords: '生成式人工智能；学术写作；导师指导；研究生培养',
    gap: '关于生成式人工智能在研究生写作中如何与导师指导协同的实证证据仍较为有限。',
    method: '研究采用写作过程追踪、文本版本比较和访谈方法，分析二十四名研究生在一个学期内的修改记录。',
    finding: '将工具反馈限定为语言与结构提示，并保留人工确认环节，能够帮助学生形成可追溯的修改说明。',
    limitation: '研究未覆盖不同学科对工具使用规范的差异。',
    corpusIndex: 2,
  },
  {
    primaryDiscipline: '公共管理学', secondaryDiscipline: '教育政策与管理', direction: '学位论文质量保障',
    keywords: '质量保障；学位论文；过程治理；制度比较',
    gap: '不同高校的论文质量保障制度虽已形成多节点安排，但节点之间的反馈衔接机制尚缺少比较分析。',
    method: '研究选取六所高校的制度文本与管理流程作为材料，采用比较案例法归纳关键治理环节。',
    finding: '将开题、中期检查和预答辩的意见纳入同一证据链，可以减少重复填报并提升质量改进的连续性。',
    limitation: '制度文本与实际执行之间仍可能存在偏差。',
    corpusIndex: 3,
  },
  {
    primaryDiscipline: '教育学', secondaryDiscipline: '研究生教育学', direction: '科研诚信与学术规范',
    keywords: '科研诚信；学术规范；导师责任；研究生培养',
    gap: '科研诚信教育常以集中培训为主，对其如何嵌入研究设计和论文修改环节的讨论仍不充分。',
    method: '研究通过问卷、焦点小组和典型案例分析，考察三个学院的科研诚信教育实施路径。',
    finding: '在选题、数据处理和论文送审前设置针对性提示，可使规范要求与具体研究行为建立更稳定的联系。',
    limitation: '学生自陈数据可能受到社会期许影响。',
    corpusIndex: 4,
  },
];

function getResearchContext(student) {
  const studentNumber = Number(String(student.id || '').match(/\d+$/)?.[0] || 1);
  return RESEARCH_CONTEXTS[(Math.max(studentNumber, 1) - 1) % RESEARCH_CONTEXTS.length];
}

function buildOriginalText(student, revisionLabel = '定稿前检查稿') {
  const context = getResearchContext(student);
  return [
    student.thesisTitle,
    revisionLabel,
    '摘要',
    `本文围绕“${student.thesisTitle}”展开研究，在梳理国内外相关成果的基础上，构建由制度规范、过程管理、反馈机制和质量改进组成的分析框架。`,
    `关键词：${context.keywords}`,
    '引言',
    context.gap,
    '研究方法',
    context.method,
    '研究结果',
    context.finding,
    '讨论',
    '不同学科在成果形态和评价重点上存在差异，统一规则应与学院补充规则结合使用，避免以单一指标替代学术判断。',
    '结论',
    `本文提出的分析框架可为校内质量保障提供参考，但${context.limitation}`,
    '参考文献',
    '[1] 李明. 高校数字治理研究[J]. 教育信息化研究, 2025(3): 12-20.',
    '[2] 王芳. 学位论文质量保障机制研究[J]. 研究生教育, 2024(6): 44-50.',
    '[3] 周宁. 研究生培养过程评价的证据链构建[J]. 高等教育研究, 2025(8): 61-69.',
  ].join('\n');
}

function isoDaysAgo(days, hour) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  date.setUTCHours(hour, 0, 0, 0);
  return date.toISOString();
}

function buildNormativeIssues(severityCounts = { high: 1, medium: 2, low: 2 }) {
  const issues = [
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

  const issueBanks = {
    high: [
      {
        rule_id: 'EVIDENCE-NUMERIC-SUPPORT',
        category: '论据支撑',
        line: 10,
        column: 1,
        excerpt: '能够提升论文质量管理的透明度与可追溯性。',
        message: '结论包含明确效果判断，但当前段落尚未给出对应统计结果或访谈证据。',
        suggestion: '补充量化结果、典型访谈编码或案例对比数据，并说明证据来源。',
      },
      {
        rule_id: 'METHOD-SAMPLE-BOUNDARY',
        category: '研究方法',
        line: 8,
        column: 1,
        excerpt: '选取三所高校的培养管理实践作为案例。',
        message: '样本选择标准和案例代表性说明不足，可能影响研究结论的适用边界。',
        suggestion: '说明案例选择依据、学校类型及样本排除标准。',
      },
    ],
    medium: [
      {
        rule_id: 'TERM-CONSISTENCY',
        category: '术语一致性',
        line: 6,
        column: 1,
        excerpt: '多主体协同、反馈时效及规则一致性',
        message: '“质量评价”“质量监测”和“质量保障”在正文中交替使用，建议明确概念关系。',
        suggestion: '在绪论中给出核心术语定义，并统一后续章节用词。',
      },
      {
        rule_id: 'ARGUMENT-TRANSITION',
        category: '论证结构',
        line: 11,
        column: 1,
        excerpt: '不同学科在成果形态和评价重点上存在差异。',
        message: '研究结果与讨论之间的过渡较快，尚未说明该判断如何由案例材料推导。',
        suggestion: '增加承上启下段落，概括结果证据并引出学科差异讨论。',
      },
    ],
    low: [
      {
        rule_id: 'KEYWORD-CONSISTENCY',
        category: '摘要与关键词',
        line: 4,
        column: 1,
        excerpt: '关键词与摘要中的核心概念',
        message: '部分关键词在摘要中的对应表述不够突出。',
        suggestion: '在摘要研究背景或结论中补充与关键词对应的具体研究视角。',
      },
      {
        rule_id: 'REFERENCE-RECENCY',
        category: '参考文献',
        line: 17,
        column: 1,
        excerpt: '[3] 周宁. 研究生培养过程评价的证据链构建[J].',
        message: '参考文献已覆盖近期研究，建议再补充一项国外相关实证成果。',
        suggestion: '检索近五年同主题外文文献并说明其与本研究的关系。',
      },
      {
        rule_id: 'ABSTRACT-METHOD-DETAIL',
        category: '摘要',
        line: 3,
        column: 1,
        excerpt: '在梳理国内外相关成果的基础上',
        message: '摘要对研究方法的交代较概括。',
        suggestion: '简要写明案例数量、访谈对象及主要分析方法。',
      },
    ],
  };

  const baseCounts = { high: 0, medium: 1, low: 2 };
  let findingIndex = issues.length + 1;
  for (const severity of ['high', 'medium', 'low']) {
    const required = Math.max(0, Number(severityCounts[severity] || 0) - baseCounts[severity]);
    for (let index = 0; index < required; index += 1) {
      const template = issueBanks[severity][index % issueBanks[severity].length];
      issues.push({
        finding_id: `finding-norm-${String(findingIndex).padStart(3, '0')}`,
        severity,
        ...template,
      });
      findingIndex += 1;
    }
  }
  return issues;
}

function buildInnovationSnapshots(student, createdAt) {
  const context = getResearchContext(student);
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
    primary_discipline: context.primaryDiscipline,
    secondary_discipline: context.secondaryDiscipline,
    research_direction: context.direction,
    research_background: buildOriginalText(student),
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

function buildDuplicationReport(student, originalText, sourceFilename, detectionType = 'campus_corpus') {
  const corpusMatches = [
    ['demo-corpus-digital-governance', '高校数字治理与质量保障案例样本', '教育管理', 2025, '构建由制度规范、过程管理、反馈机制和质量改进组成的分析框架。', '形成可解释、可追溯的质量评价框架'],
    ['demo-corpus-graduate-writing', '研究生学术写作规范案例样本', '研究生教育', 2024, '持续呈现任务完成节奏和反馈响应情况。', '形成持续修改记录'],
    ['demo-corpus-ai-education', '生成式人工智能教育应用案例样本', '教育技术', 2026, '保留人工确认环节，能够帮助学生形成可追溯的修改说明。', '评价结果必须保持可解释性'],
    ['demo-corpus-process-evaluation', '研究生培养过程评价与反馈机制研究', '高等教育管理', 2025, '将开题、中期检查和预答辩的意见纳入同一证据链。', '形成可复核的修改证据链'],
    ['demo-corpus-research-integrity', '高校科研诚信教育实施路径案例', '科研管理', 2024, '在选题、数据处理和论文送审前设置针对性提示。', '融入研究设计、数据采集、论文写作全过程'],
  ];
  const [sampleId, title, subject, year, sourceExcerpt, sampleExcerpt] = corpusMatches[getResearchContext(student).corpusIndex];
  const isAigcRisk = detectionType === 'aigc_writing_risk';
  return {
    status: 'completed',
    detection_type: detectionType,
    detection_type_label: isAigcRisk ? 'AIGC 写作风险检测' : '校内库查重',
    detection_description: isAigcRisk
      ? '演示数据：根据文本特征生成写作风险提示，不构成 AI 生成真伪结论。'
      : '演示数据：与试点本地样本库进行相似片段比对。',
    source_type: 'file',
    source_filename: sourceFilename,
    threshold: 0.3,
    effective_character_count: originalText.length,
    total_similarity_rate: isAigcRisk ? 0 : student.similarityRate,
    sample_count: isAigcRisk ? 0 : 8,
    top_matches: isAigcRisk ? [] : [
      {
        sample_id: sampleId,
        title,
        subject,
        year,
        jaccard_score: student.similarityRate,
        matched_character_count: 42,
        segments: [
          {
            source_start: 28,
            source_end: 70,
            sample_start: 15,
            sample_end: 57,
            source_excerpt: sourceExcerpt,
            sample_excerpt: sampleExcerpt,
          },
        ],
      },
    ],
    risk: {
      score: Math.round(student.similarityRate * 100),
      label: 'heuristic_only',
      explanation: isAigcRisk
        ? '演示数据：写作风险分仅依据重复、句式和模板化表达等文本特征计算，并非 AI 真伪结论。'
        : '演示数据：风险分仅依据本地样本相似片段和文本特征计算。',
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

async function updateDemoRows(tx, summary, category, sql, params) {
  const result = await tx.run(sql, params);
  summary.updated += result.changes;
  summary.updated_by_category[category] = (summary.updated_by_category[category] || 0) + result.changes;
}

async function normalizeLegacyDemoLabels(tx, summary) {
  const profiles = QUALITY_STUDENTS;

  for (const profile of profiles) {
    const sourceFilename = `${profile.thesisTitle}_定稿前检查稿.pdf`;
    const originalText = buildOriginalText(profile);
    const issues = buildNormativeIssues(profile.severityCounts);
    const duplicationReport = buildDuplicationReport(profile, originalText, sourceFilename);
    const { inputSnapshot, scoringSnapshot } = buildInnovationSnapshots(profile, isoDaysAgo(2, 4));

    await updateDemoRows(
      tx,
      summary,
      'normative',
      `UPDATE normative_detection_tasks
          SET source_filename = ?, original_text = ?, issues_json = ?, severity_counts_json = ?
        WHERE id = ? AND source_filename LIKE '[演示]%'`,
      [
        sourceFilename,
        originalText,
        JSON.stringify(issues),
        JSON.stringify(profile.severityCounts),
        `demo-normative-${profile.id}`,
      ],
    );
    await updateDemoRows(
      tx,
      summary,
      'duplication',
      `UPDATE duplication_detection_reports
          SET source_filename = ?, original_text = ?, sample_count = 5, report_json = ?
        WHERE id = ? AND source_filename LIKE '[演示]%'`,
      [sourceFilename, originalText, JSON.stringify(duplicationReport), `demo-duplication-${profile.id}`],
    );
    await updateDemoRows(
      tx,
      summary,
      'ai_review',
      `UPDATE ai_review_runs
          SET thesis_title = ?, source_filename = ?, original_text = ?, character_count = ?, normative_issues_json = ?
        WHERE id = ? AND (source_filename LIKE '[演示]%' OR thesis_title LIKE '%演示%')`,
      [
        profile.thesisTitle,
        sourceFilename,
        originalText,
        originalText.length,
        JSON.stringify(issues.slice(0, 3)),
        `demo-ai-review-${profile.id}`,
      ],
    );
    await updateDemoRows(
      tx,
      summary,
      'innovation',
      `UPDATE innovation_assessment_snapshots
          SET thesis_title = ?, input_snapshot_json = ?, scoring_snapshot_json = ?
        WHERE id = ? AND thesis_title LIKE '%演示%'`,
      [
        profile.thesisTitle,
        JSON.stringify(inputSnapshot),
        JSON.stringify(scoringSnapshot),
        `demo-innovation-${profile.id}`,
      ],
    );
  }

  await updateDemoRows(
    tx,
    summary,
    'whole_polish',
    `UPDATE whole_polish_results
        SET source_filename = ?
      WHERE id = ? AND source_filename LIKE '[演示]%'`,
    [`${QUALITY_STUDENTS[0].thesisTitle}_语言修改稿.docx`, 'demo-whole-polish-student01'],
  );
}

async function seedHelperSupervisors(tx, summary) {
  for (const supervisor of SUPERVISOR_PROFILES) {
    await insertDemoRow(
      tx,
      summary,
      'users',
      `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
       SELECT ?, ?, password_hash, 'SUPERVISOR', ?, NULL, 'COLLEGE'
         FROM auth_users
        WHERE username = 'supervisor01'
       ON CONFLICT(username) DO NOTHING`,
      [supervisor.id, supervisor.id, supervisor.collegeId],
    );
  }
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
    {
      id: 'demo-corpus-process-evaluation',
      title: '研究生培养过程评价与反馈机制研究',
      subject: '高等教育管理',
      year: 2025,
      content:
        '培养过程评价应记录选题、开题、中期检查、预答辩和送审等关键节点，以持续反馈替代单一结果评价，并形成可复核的修改证据链。',
    },
    {
      id: 'demo-corpus-research-integrity',
      title: '高校科研诚信教育实施路径案例',
      subject: '科研管理',
      year: 2024,
      content:
        '科研诚信教育需要融入研究设计、数据采集、论文写作和成果发布全过程，通过导师指导、规则教育和案例警示提升研究者的责任意识。',
    },
    {
      id: 'demo-corpus-education-evaluation',
      title: '教育评价数字化转型研究样本',
      subject: '教育学',
      year: 2023,
      content:
        '教育评价数字化转型应同时关注数据质量、指标解释和结果反馈，避免将单一量化分数直接替代对学习过程与研究成果的综合判断。',
    },
    {
      id: 'demo-corpus-public-policy',
      title: '公共政策协同治理案例样本',
      subject: '公共管理',
      year: 2024,
      content:
        '协同治理需要明确责任边界、信息共享机制和反馈时限，并通过阶段性评估识别执行偏差，为后续政策调整提供可追溯的证据。',
    },
    {
      id: 'demo-corpus-learning-analytics',
      title: '学习分析支持课程改进研究样本',
      subject: '教育技术学',
      year: 2025,
      content:
        '学习分析应将任务完成节奏、互动质量和反馈响应情况结合起来解释，教师需要结合课程目标与学生实际情况开展人工复核。',
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

async function seedQualityRecordSet(tx, summary, student, index, options = {}) {
  const context = getResearchContext(student);
  const recordKey = options.recordKey ? `${student.id}-${options.recordKey}` : student.id;
  const revisionLabel = options.revisionLabel || '定稿前检查稿';
  const displayTitle = options.recordKey ? `${student.thesisTitle}（${revisionLabel}）` : student.thesisTitle;
  const sourceFilename = `${student.thesisTitle}_${revisionLabel}.pdf`;
  const baseDaysAgo = options.daysAgo;
  const normativeCreatedAt = isoDaysAgo(baseDaysAgo ?? 3 - Math.min(index, 3), 2);
  const duplicationCreatedAt = isoDaysAgo(baseDaysAgo ?? 3 - Math.min(index, 3), 3);
  const innovationCreatedAt = isoDaysAgo(baseDaysAgo ?? 2 - Math.min(index, 2), 4);
  const reviewCreatedAt = isoDaysAgo(baseDaysAgo ?? 1 - Math.min(index, 1), 5);
  const originalText = buildOriginalText(student, revisionLabel);
  const normativeIssues = buildNormativeIssues(student.severityCounts);
    const duplicationReport = buildDuplicationReport(
      student,
      originalText,
      sourceFilename,
      index % 2 === 0 ? 'campus_corpus' : 'aigc_writing_risk',
    );
  const { inputSnapshot, scoringSnapshot } = buildInnovationSnapshots(
    { ...student, thesisTitle: displayTitle },
    innovationCreatedAt,
  );
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
      `demo-normative-${recordKey}`,
      student.id,
      sourceFilename,
      originalText,
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
       ) VALUES (?, ?, 'file', ?, ?, ?, ?, ?, ?, ?)`,
    [
      `demo-duplication-${recordKey}`,
      student.id,
      sourceFilename,
      originalText,
      duplicationReport.total_similarity_rate,
      Math.round(student.similarityRate * 100 + 16),
      duplicationReport.sample_count,
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
     ) VALUES (?, ?, ?, 'master', ?, ?, ?, ?, ?, ?)`,
    [
      `demo-innovation-${recordKey}`,
      student.id,
      displayTitle,
      context.primaryDiscipline,
      context.secondaryDiscipline,
      context.direction,
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
      `demo-ai-review-${recordKey}`,
      student.id,
      displayTitle,
      sourceFilename,
      originalText,
      JSON.stringify([
        { name: '摘要', present: true },
        { name: '关键词', present: true },
        { name: '引言', present: true },
        { name: '研究方法', present: true },
        { name: '结论', present: true },
        { name: '参考文献', present: true },
      ]),
      originalText.length,
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

async function seedStudentHistorySeries(tx, summary) {
  const baseStudent = QUALITY_STUDENTS[0];
  for (const [index, round] of STUDENT_HISTORY_ROUNDS.entries()) {
    await seedQualityRecordSet(
      tx,
      summary,
      {
        ...baseStudent,
        levels: round.levels,
        similarityRate: round.similarityRate,
        reviewScore: round.reviewScore,
        severityCounts: round.severityCounts,
      },
      index,
      {
        recordKey: round.key,
        revisionLabel: round.label,
        daysAgo: round.daysAgo,
      },
    );
  }
}

async function seedPolishHistory(tx, summary, userId, index) {
  const documentTitle = QUALITY_STUDENTS[0].thesisTitle;
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
      `${documentTitle}_语言修改稿.docx`,
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

async function seedAdditionalStudentPolishHistory(tx, summary) {
  const title = QUALITY_STUDENTS[0].thesisTitle;
  const wholeRecords = [
    {
      id: 'demo-whole-polish-student01-literature',
      filename: `${title}_文献综述修订稿.docx`,
      original: '已有研究从不同不同角度讨论了高校数字治理，因此所以相关成果较为丰富，但对过程质量证据的关注不够。',
      polished: '已有研究从不同角度讨论了高校数字治理，相关成果较为丰富，但对过程质量证据的关注仍显不足。',
      level: 'enhanced',
      daysAgo: 17,
    },
    {
      id: 'demo-whole-polish-student01-conclusion',
      filename: `${title}_结论章节修改稿.docx`,
      original: '综上所述，本研究得出了相关相关结论。这个结论是非常重要的，对学校管理具有一定的意义。',
      polished:
        '综上，本研究归纳了过程质量评价的关键影响因素，并据此提出分阶段反馈机制，为高校完善论文质量管理提供参考。',
      level: 'standard',
      daysAgo: 8,
    },
  ];
  for (const record of wholeRecords) {
    await insertDemoRow(
      tx,
      summary,
      'whole_polish',
      `INSERT OR IGNORE INTO whole_polish_results (
         id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json, created_at
       ) VALUES (?, 'student01', 'file', ?, ?, ?, ?, ?, ?)`,
      [
        record.id,
        record.filename,
        record.original,
        record.polished,
        record.level,
        JSON.stringify([
          {
            original_text: record.original,
            new_text: record.polished,
            position: 0,
            rule: '学术表达与逻辑衔接优化',
            reason: '删除重复表达，并将概括性判断改写为与研究结论对应的陈述。',
          },
        ]),
        isoDaysAgo(record.daysAgo, 7),
      ],
    );
  }

  await insertDemoRow(
    tx,
    summary,
    'local_polish',
    `INSERT OR IGNORE INTO local_polish_results (
       id, user_id, original_text, polished_text, level, rule_version, changes_json,
       diff_segments_json, source_result_id, retry_of, created_at
     ) VALUES ('demo-local-polish-student01-method', 'student01', ?, ?, 'enhanced',
       'local-polish-rules-v1', ?, ?, NULL, NULL, ?)`,
    [
      '本研究一共总计访谈了二十八名访谈对象，并且对访谈资料进行了相关的编码分析。',
      '本研究共访谈二十八名研究参与者，并对访谈资料进行主题编码分析。',
      JSON.stringify([
        {
          original_text: '一共总计',
          new_text: '共',
          position: 3,
          rule: '语义重复优化',
        },
        {
          original_text: '访谈对象，并且对访谈资料进行了相关的编码分析',
          new_text: '研究参与者，并对访谈资料进行主题编码分析',
          position: 11,
          rule: '学术表达优化',
        },
      ]),
      JSON.stringify([
        { type: 'unchanged', text: '本研究', position: 0 },
        { type: 'replacement', original_text: '一共总计', new_text: '共', text: '共', position: 3 },
        { type: 'unchanged', text: '访谈了二十八名', position: 7 },
        {
          type: 'replacement',
          original_text: '访谈对象，并且对访谈资料进行了相关的编码分析',
          new_text: '研究参与者，并对访谈资料进行主题编码分析',
          text: '研究参与者，并对访谈资料进行主题编码分析',
          position: 14,
        },
      ]),
      isoDaysAgo(5, 7),
    ],
  );
}

async function seedReviewWorkflow(tx, summary) {
  const submissions = [
    {
      id: 'demo-submission-pending',
      batchId: 'demo-batch-round-3',
      reportId: 'demo-normative-student01',
      status: 'submitted_pending_review',
      todoStatus: 'pending',
      title: '《高校数字治理质量评价体系研究》第三轮待批阅',
      createdAt: isoDaysAgo(0, 8),
    },
    {
      id: 'demo-submission-feedback',
      batchId: 'demo-batch-round-2',
      reportId: 'demo-normative-student01-pre-defense',
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
      reportId: 'demo-normative-student01-midterm-revision',
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
    {
      id: 'demo-submission-viewed-method',
      batchId: 'demo-batch-method-review',
      reportId: 'demo-normative-student01-chapter-review',
      status: 'student_viewed_feedback',
      todoStatus: 'done',
      title: '《高校数字治理质量评价体系研究》研究方法专项批阅',
      createdAt: isoDaysAgo(14, 8),
      feedback: {
        id: 'demo-feedback-method-review',
        lockedAt: isoDaysAgo(13, 3),
        annotations: [
          {
            finding_id: 'finding-norm-004',
            comment: '案例数量已经明确，请进一步交代学校类型、访谈对象构成和编码一致性检验过程。',
          },
        ],
        overallEvaluation: '研究设计基本可行，方法章节已形成完整结构，样本选择与分析过程仍需补足复核信息。',
        improvementSuggestions: '增加样本结构表和访谈提纲说明，并给出主题编码形成过程及代表性原始材料。',
      },
    },
    {
      id: 'demo-submission-viewed-literature',
      batchId: 'demo-batch-literature-review',
      reportId: 'demo-normative-student01-proposal-revision',
      status: 'student_viewed_feedback',
      todoStatus: 'done',
      title: '《高校数字治理质量评价体系研究》文献综述专项批阅',
      createdAt: isoDaysAgo(29, 8),
      feedback: {
        id: 'demo-feedback-literature-review',
        lockedAt: isoDaysAgo(28, 3),
        annotations: [
          {
            finding_id: 'finding-norm-002',
            comment: '国内研究梳理较充分，建议增加过程评价和证据链相关的国外实证研究，并形成比较维度。',
          },
        ],
        overallEvaluation: '文献综述已覆盖论文质量保障和数字治理两条研究脉络，但研究缺口的推导还可以更集中。',
        improvementSuggestions: '以“评价主体、评价节点、证据类型、反馈应用”四个维度重组文献评述，并据此提出研究问题。',
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
      [item.id, item.batchId, item.reportId, item.status, item.createdAt],
    );
    await updateDemoRows(
      tx,
      summary,
      'submissions',
      'UPDATE report_submissions SET report_id = ? WHERE id = ? AND report_id <> ?',
      [item.reportId, item.id, item.reportId],
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

async function removeLegacyNonStudentHistories(tx, summary) {
  const legacyUserIds = DEMO_USER_IDS.filter((userId) => userId !== 'student01');
  const placeholders = legacyUserIds.map(() => '?').join(', ');
  const tables = [
    ['normative', 'normative_detection_tasks'],
    ['duplication', 'duplication_detection_reports'],
    ['innovation', 'innovation_assessment_snapshots'],
    ['ai_review', 'ai_review_runs'],
    ['whole_polish', 'whole_polish_results'],
    ['local_polish', 'local_polish_results'],
  ];

  for (const [category, table] of tables) {
    const result = await tx.run(`DELETE FROM ${table} WHERE user_id IN (${placeholders}) AND id LIKE 'demo-%'`, legacyUserIds);
    summary.removed += result.changes;
    summary.removed_by_category[category] = (summary.removed_by_category[category] || 0) + result.changes;
  }
}

async function verifyDemoData(tx) {
  const [missingSupervisors, mismatchedSubmissions] = await Promise.all([
    tx.all(
      `SELECT student.id
         FROM auth_users student
         LEFT JOIN auth_users supervisor ON supervisor.id = student.supervisor_id AND supervisor.role = 'SUPERVISOR'
        WHERE student.id LIKE 'student%' AND student.role = 'STUDENT' AND supervisor.id IS NULL`,
    ),
    tx.all(
      `SELECT submission.id
         FROM report_submissions submission
         LEFT JOIN normative_detection_tasks report ON report.id = submission.report_id AND report.user_id = submission.student_id
        WHERE submission.id LIKE 'demo-submission-%' AND submission.source_type = 'normative' AND report.id IS NULL`,
    ),
  ]);

  const problems = [
    ...missingSupervisors.map((row) => `学生 ${row.id} 缺少有效导师`),
    ...mismatchedSubmissions.map((row) => `批阅任务 ${row.id} 未关联学生本人的报告`),
  ];
  if (problems.length > 0) {
    throw new Error(`演示数据校验失败：${problems.join('；')}`);
  }
  return { valid: true, checked: ['student-supervisor', 'submission-report'] };
}

async function seedDemoDatabase(options = {}) {
  if (options.confirmDemoData !== true) {
    throw new Error('演示数据初始化需要显式传入 confirmDemoData: true');
  }

  await seedDatabase();
  return withTransaction(async (tx) => {
    const summary = {
      inserted: 0,
      updated: 0,
      removed: 0,
      by_category: {},
      updated_by_category: {},
      removed_by_category: {},
    };
    await removeLegacyNonStudentHistories(tx, summary);
    await seedHelperSupervisors(tx, summary);
    await seedHelperStudents(tx, summary);
    await seedCorpus(tx, summary);

    for (const [index, student] of QUALITY_STUDENTS.entries()) {
      await seedQualityRecordSet(tx, summary, student, index);
    }
    await seedStudentHistorySeries(tx, summary);
    await seedPolishHistory(tx, summary, 'student01', 0);
    await seedAdditionalStudentPolishHistory(tx, summary);
    await seedReviewWorkflow(tx, summary);
    await normalizeLegacyDemoLabels(tx, summary);

    await insertDemoRow(
      tx,
      summary,
      'metadata',
      `INSERT INTO demo_seed_metadata (demo_key, version, seeded_at)
       VALUES ('presentation-full', ?, CURRENT_TIMESTAMP)
       ON CONFLICT(demo_key) DO UPDATE SET version = excluded.version, seeded_at = excluded.seeded_at
       WHERE demo_seed_metadata.version <> excluded.version`,
      [DEMO_SEED_VERSION],
    );
    const verification = await verifyDemoData(tx);

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
    return { ...summary, version: DEMO_SEED_VERSION, verification, totals };
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
  DEMO_SEED_VERSION,
  DEMO_USER_IDS,
  SUPERVISOR_PROFILES,
  QUALITY_STUDENTS,
  seedDemoDatabase,
};
