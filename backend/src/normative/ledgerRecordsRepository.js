const { all, get } = require('../database');

const DETECTION_TYPE_LABELS = {
  normative: '规范性检测',
  duplication: '校内库查重',
  ai_review: 'AI智能评阅',
  aigc: 'AIGC查重',
  polish: '全文润色',
  innovation: '创新性分析',
};

function normalizeLedgerFilters(filters = {}) {
  return {
    student: typeof filters.student === 'string' ? filters.student.trim() : '',
    detection_type: typeof filters.detection_type === 'string' ? filters.detection_type.trim() : '',
    from: typeof filters.from === 'string' ? filters.from.trim() : '',
    to: typeof filters.to === 'string' ? filters.to.trim() : '',
    latest_only: filters.latest_only === true || filters.latest_only === 'true',
  };
}

function buildScopeWhere(scope, params) {
  if (scope?.role === 'SUPERVISOR') {
    params.push(scope.supervisor_id);
    return 'u.supervisor_id = ?';
  }
  if (scope?.role === 'COLLEGE_ADMIN') {
    params.push(scope.college_id);
    return 'u.college_id = ?';
  }
  return '1 = 1';
}

function buildFilteredLedgerSql(scope, filters = {}, options = {}) {
  const params = [];
  const where = ["u.role = 'STUDENT'", buildScopeWhere(scope, params)];

  if (filters.detection_type) {
    where.push('ledger.detection_type = ?');
    params.push(filters.detection_type);
  }
  if (filters.from) {
    where.push('date(ledger.created_at) >= date(?)');
    params.push(filters.from);
  }
  if (filters.to) {
    where.push('date(ledger.created_at) <= date(?)');
    params.push(filters.to);
  }
  if (filters.student) {
    const keyword = `%${filters.student}%`;
    where.push(`(
      u.id LIKE ?
      OR u.username LIKE ?
      OR ledger.thesis_title LIKE ?
      OR ledger.source_filename LIKE ?
    )`);
    params.push(keyword, keyword, keyword, keyword);
  }
  if (filters.latest_only) {
    where.push('ledger.latest_rank = 1');
  }

  const sql = `
    WITH ledger AS (
      SELECT
        'normative:' || task.id AS id,
        task.id AS source_record_id,
        task.user_id AS student_id,
        COALESCE(task.source_filename, '规范性检测') AS thesis_title,
        task.source_filename,
        'normative' AS detection_type,
        '规范性检测' AS detection_type_label,
        COALESCE(json_extract(task.rule_snapshot_json, '$[0].title'), '规范检测模板') AS template_name,
        '发现 ' || COALESCE(json_array_length(task.issues_json), 0) || ' 项格式问题' AS core_result,
        '/normative-reports/' || task.id AS detail_url,
        task.created_at AS created_at,
        ROW_NUMBER() OVER (PARTITION BY task.user_id, 'normative' ORDER BY datetime(task.created_at) DESC, task.created_at DESC) AS latest_rank
      FROM normative_detection_tasks task
      WHERE task.status = 'completed'

      UNION ALL

      SELECT
        'duplication:' || report.id AS id,
        report.id AS source_record_id,
        report.user_id AS student_id,
        COALESCE(report.source_filename, '校内库查重') AS thesis_title,
        report.source_filename,
        'duplication' AS detection_type,
        '校内库查重' AS detection_type_label,
        '校内库查重报告' AS template_name,
        '相似度 ' || ROUND(report.total_similarity_rate * 100, 1) || '%' AS core_result,
        '/duplication-history/' || report.id AS detail_url,
        report.created_at AS created_at,
        ROW_NUMBER() OVER (PARTITION BY report.user_id, 'duplication' ORDER BY datetime(report.created_at) DESC, report.created_at DESC) AS latest_rank
      FROM duplication_detection_reports report

      UNION ALL

      SELECT
        'ai_review:' || review.id AS id,
        review.id AS source_record_id,
        review.user_id AS student_id,
        review.thesis_title AS thesis_title,
        review.source_filename,
        'ai_review' AS detection_type,
        'AI智能评阅' AS detection_type_label,
        review.template_id AS template_name,
        review.result_label || '（' || review.total_score || '分）' AS core_result,
        '/ai-review/results/' || review.id AS detail_url,
        review.created_at AS created_at,
        ROW_NUMBER() OVER (PARTITION BY review.user_id, 'ai_review' ORDER BY datetime(review.created_at) DESC, review.created_at DESC) AS latest_rank
      FROM ai_review_runs review
    )
    SELECT
      ledger.*,
      u.college_id,
      COALESCE(u.college_id, '全校') AS college_name,
      u.id AS student_number,
      u.username AS student_name,
      u.supervisor_id,
      COALESCE(supervisor.username, u.supervisor_id, '') AS supervisor_name,
      CASE WHEN u.role = 'STUDENT' THEN '学生' ELSE u.role END AS student_category,
      CASE WHEN ledger.latest_rank = 1 THEN 1 ELSE 0 END AS is_latest
    FROM ledger
    JOIN auth_users u ON u.id = ledger.student_id
    LEFT JOIN auth_users supervisor ON supervisor.id = u.supervisor_id
    WHERE ${where.join(' AND ')}
    ORDER BY datetime(ledger.created_at) DESC, ledger.created_at DESC${options.limitOne ? ' LIMIT 1' : ''};
  `;

  return { sql, params };
}

function mapLedgerRow(row) {
  return {
    id: row.id,
    source_record_id: row.source_record_id,
    college_id: row.college_id || null,
    college_name: row.college_name,
    student_id: row.student_id,
    student_number: row.student_number,
    student_name: row.student_name,
    supervisor_id: row.supervisor_id || null,
    supervisor_name: row.supervisor_name || '',
    student_category: row.student_category,
    thesis_title: row.thesis_title,
    detection_type: row.detection_type,
    detection_type_label: row.detection_type_label || DETECTION_TYPE_LABELS[row.detection_type] || row.detection_type,
    template_name: row.template_name,
    core_result: row.core_result,
    detail_url: row.detail_url,
    is_latest: Boolean(row.is_latest),
    created_at: row.created_at,
  };
}

async function listLedgerRecords(scope, filters = {}) {
  const normalizedFilters = normalizeLedgerFilters(filters);
  const { sql, params } = buildFilteredLedgerSql(scope, normalizedFilters);
  const rows = await all(sql, params);
  return rows.map(mapLedgerRow);
}

async function findLedgerRecordById(scope, recordId) {
  const normalizedRecordId = String(recordId || '').trim();
  if (!normalizedRecordId) {
    return null;
  }

  const allScopedRecords = await listLedgerRecords(scope, {
    latest_only: false,
  });
  return (
    allScopedRecords.find(
      (record) => record.id === normalizedRecordId || record.source_record_id === normalizedRecordId,
    ) || null
  );
}

function uniqueStudentCount(records) {
  return new Set(records.map((record) => record.student_id)).size;
}

function buildTypeStats(records, today) {
  const statsByType = new Map();

  records.forEach((record) => {
    if (!statsByType.has(record.detection_type)) {
      statsByType.set(record.detection_type, {
        detection_type: record.detection_type,
        detection_type_label: record.detection_type_label,
        records: [],
      });
    }
    statsByType.get(record.detection_type).records.push(record);
  });

  return Array.from(statsByType.values()).map((bucket) => {
    const recordCount = bucket.records.length;
    const studentCount = uniqueStudentCount(bucket.records);
    const todayCount = bucket.records.filter((record) => record.created_at.slice(0, 10) === today).length;
    return {
      detection_type: bucket.detection_type,
      detection_type_label: bucket.detection_type_label,
      record_count: recordCount,
      student_count: studentCount,
      total_records: recordCount,
      total_students: studentCount,
      today_count: todayCount,
    };
  });
}

function buildDailyTrend(records) {
  const statsByDate = new Map();

  records.forEach((record) => {
    const date = record.created_at.slice(0, 10);
    if (!statsByDate.has(date)) {
      statsByDate.set(date, []);
    }
    statsByDate.get(date).push(record);
  });

  return Array.from(statsByDate.entries())
    .sort(([leftDate], [rightDate]) => leftDate.localeCompare(rightDate))
    .map(([date, dateRecords]) => {
      const recordCount = dateRecords.length;
      const studentCount = uniqueStudentCount(dateRecords);
      return {
        date,
        count: recordCount,
        record_count: recordCount,
        student_count: studentCount,
        total_records: recordCount,
        total_students: studentCount,
      };
    });
}

async function summarizeLedgerRecords(scope, filters = {}) {
  const normalizedFilters = normalizeLedgerFilters(filters);
  const records = await listLedgerRecords(scope, normalizedFilters);
  const today = new Date().toISOString().slice(0, 10);

  return {
    filters: normalizedFilters,
    total_records: records.length,
    total_students: uniqueStudentCount(records),
    today_count: records.filter((record) => record.created_at.slice(0, 10) === today).length,
    by_type: buildTypeStats(records, today),
    daily_trend: buildDailyTrend(records),
    generated_at: new Date().toISOString(),
  };
}

module.exports = {
  findLedgerRecordById,
  listLedgerRecords,
  normalizeLedgerFilters,
  summarizeLedgerRecords,
};
