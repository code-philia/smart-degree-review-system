const DEFAULT_NORMATIVE_RULES = Object.freeze([
  { rule_id: 'NORM-001', category: '章节顺序', title: '摘要、关键词、引言、结论、参考文献必须按顺序出现' },
  { rule_id: 'NORM-002', category: '标点配对', title: '检查中英文圆括号、方括号、书名号和引号是否成对' },
  { rule_id: 'NORM-003', category: '重复标点', title: '报告“，，”“。。”“；；”和连续三个以上相同标点' },
  { rule_id: 'NORM-004', category: '日期格式', title: '数字日期仅接受 YYYY-MM-DD' },
  { rule_id: 'NORM-005', category: '参考文献', title: '参考文献后的非空行必须以 [1] 开始并连续递增' },
  { rule_id: 'NORM-006', category: '文本质量', title: '报告连续重复词、Tab、行尾空格、超过 120 个字符的句子以及禁用词' },
]);

const REQUIRED_SECTION_ORDER = ['摘要', '关键词', '引言', '结论', '参考文献'];
const DEFAULT_DISABLED_WORDS = ['显然', '众所周知', '必须'];
const OPEN_TO_CLOSE = new Map([
  ['(', ')'],
  ['（', '）'],
  ['[', ']'],
  ['【', '】'],
  ['《', '》'],
  ['“', '”'],
  ['"', '"'],
  ["'", "'"],
]);
const CLOSE_TO_OPEN = new Map(Array.from(OPEN_TO_CLOSE.entries()).map(([open, close]) => [close, open]));
const PUNCTUATION_RUN_CHARS = /[，。；！？!?,.、:;：…·~—-]/u;

function createIssue(rule_id, category, severity, line, column, excerpt, message, suggestion) {
  return { rule_id, category, severity, line, column, excerpt, message, suggestion };
}

function normalizeLines(text) {
  return text.split(/\r?\n/);
}

function getLineColumn(text, index) {
  const prefix = text.slice(0, index);
  const lines = prefix.split(/\r?\n/);
  const line = lines.length;
  const column = lines[lines.length - 1].length + 1;
  return { line, column };
}

function getExcerpt(text, start, end) {
  const excerpt = text.slice(start, end).replace(/\r?\n/g, ' ');
  return excerpt.length > 40 ? `${excerpt.slice(0, 37)}…` : excerpt;
}

function addIssue(issues, issue) {
  issues.push(issue);
}

function detectSectionOrder(lines, issues) {
  const positions = new Map();

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    for (const section of REQUIRED_SECTION_ORDER) {
      if (!positions.has(section) && trimmed === section) {
        positions.set(section, index);
      }
    }
  });

  let previousIndex = -1;
  for (const section of REQUIRED_SECTION_ORDER) {
    const foundIndex = positions.has(section) ? positions.get(section) : -1;
    if (foundIndex === -1) {
      addIssue(
        issues,
        createIssue(
          'NORM-001',
          '章节顺序',
          'high',
          1,
          1,
          section,
          `缺少必需章节：${section}`,
          `补充“${section}”并按规定顺序排列`,
        ),
      );
      continue;
    }
    if (foundIndex < previousIndex) {
      addIssue(
        issues,
        createIssue(
          'NORM-001',
          '章节顺序',
          'high',
          foundIndex + 1,
          1,
          section,
          `章节“${section}”顺序错误`,
          '请按照“摘要、关键词、引言、结论、参考文献”的顺序调整章节',
        ),
      );
    }
    previousIndex = Math.max(previousIndex, foundIndex);
  }
}

function detectUnmatchedPairs(text, issues) {
  const stack = [];

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const open = OPEN_TO_CLOSE.get(char);
    const close = CLOSE_TO_OPEN.get(char);

    if (open) {
      stack.push({ char, expected: open, index });
      continue;
    }

    if (!close) {
      continue;
    }

    if (stack.length && stack[stack.length - 1].expected === char) {
      stack.pop();
      continue;
    }

    const { line, column } = getLineColumn(text, index);
    addIssue(
      issues,
      createIssue(
        'NORM-002',
        '标点配对',
        'high',
        line,
        column,
        text.slice(index, index + 1),
        `多余的闭合标点“${char}”`,
        '删除多余的闭合标点，或补全相应的左侧标点',
      ),
    );
  }

  for (const entry of stack) {
    const { line, column } = getLineColumn(text, entry.index);
    addIssue(
      issues,
      createIssue(
        'NORM-002',
        '标点配对',
        'high',
        line,
        column,
        text.slice(entry.index, entry.index + 1),
        `标点“${entry.char}”未成对`,
        `补全与“${entry.char}”配对的闭合标点`,
      ),
    );
  }
}

function detectRepeatedPunctuation(lines, text, issues) {
  const exactTargets = new Map([
    ['，', '，，'],
    ['。', '。。'],
    ['；', '；；'],
  ]);

  lines.forEach((line, lineIndex) => {
    for (let columnIndex = 0; columnIndex < line.length; ) {
      const char = line[columnIndex];
      let end = columnIndex + 1;
      while (end < line.length && line[end] === char) {
        end += 1;
      }

      const runLength = end - columnIndex;
      const substring = line.slice(columnIndex, end);

      if (exactTargets.has(char) && runLength >= 2) {
        addIssue(
          issues,
          createIssue(
            'NORM-003',
            '重复标点',
            'medium',
            lineIndex + 1,
            columnIndex + 1,
            substring.slice(0, 2),
            `存在重复标点“${substring.slice(0, 2)}”`,
            '保留一个标点即可',
          ),
        );
      }

      if (PUNCTUATION_RUN_CHARS.test(char) && runLength >= 3) {
        addIssue(
          issues,
          createIssue(
            'NORM-003',
            '重复标点',
            'medium',
            lineIndex + 1,
            columnIndex + 1,
            substring,
            `存在连续 ${runLength} 个相同标点`,
            '减少重复标点并保留一个规范标点',
          ),
        );
      }

      columnIndex = end;
    }
  });
}

function detectInvalidDates(lines, issues) {
  const datePattern = /(?<!\d)\d{4}[-\/]\d{1,2}[-\/]\d{1,2}(?!\d)/g;

  lines.forEach((line, lineIndex) => {
    for (const match of line.matchAll(datePattern)) {
      const value = match[0];
      if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        continue;
      }

      addIssue(
        issues,
        createIssue(
          'NORM-004',
          '日期格式',
          'low',
          lineIndex + 1,
          match.index + 1,
          value,
          `数字日期格式不符合 YYYY-MM-DD：${value}`,
          '改为 YYYY-MM-DD，例如 2026-08-03',
        ),
      );
    }
  });
}

function detectReferenceNumbering(lines, issues) {
  const referenceIndex = lines.findIndex((line) => line.trim() === '参考文献');
  if (referenceIndex === -1) {
    return;
  }

  let expected = 1;
  for (let lineIndex = referenceIndex + 1; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    if (!line.trim()) {
      continue;
    }

    const match = line.match(/^\s*\[(\d+)\]/);
    const actual = match ? Number(match[1]) : null;
    const column = match ? match.index + 1 : line.search(/\S/) + 1;

    if (actual !== expected) {
      addIssue(
        issues,
        createIssue(
          'NORM-005',
          '参考文献',
          'medium',
          lineIndex + 1,
          column > 0 ? column : 1,
          line.trim(),
          actual === null
            ? `参考文献第 ${expected} 条格式不正确`
            : `参考文献编号应为 [${expected}]，但找到了 [${actual}]`,
          expected === 1
            ? '第一条参考文献应以 [1] 开始'
            : `下一条参考文献应连续编号为 [${expected}]`,
        ),
      );
    }

    if (actual !== null) {
      expected = actual + 1;
    } else {
      expected += 1;
    }
  }
}

function detectTextQuality(lines, text, issues) {
  lines.forEach((line, lineIndex) => {
    const tabIndex = line.indexOf('\t');
    if (tabIndex !== -1) {
      addIssue(
        issues,
        createIssue(
          'NORM-006',
          '文本质量',
          'medium',
          lineIndex + 1,
          tabIndex + 1,
          '\t',
          '包含 Tab 字符',
          '使用空格替代 Tab',
        ),
      );
    }

    if (/[ \t]+$/.test(line) && line.length > 0) {
      addIssue(
        issues,
        createIssue(
          'NORM-006',
          '文本质量',
          'medium',
          lineIndex + 1,
          line.replace(/\S.*?$/, '').length + 1,
          line.slice(Math.max(0, line.replace(/\s+$/, '').length)),
          '存在行尾空格或制表符',
          '删除行尾空白字符',
        ),
      );
    }

    const repeatedWordPattern = /(^|\s)([\p{L}\p{Script=Han}\d]+)(?:\s+\2)+/gu;
    for (const match of line.matchAll(repeatedWordPattern)) {
      const start = match.index + (match[1] ? match[1].length : 0);
      addIssue(
        issues,
        createIssue(
          'NORM-006',
          '文本质量',
          'medium',
          lineIndex + 1,
          start + 1,
          line.slice(start, start + match[2].length * 2 + 1),
          `存在连续重复词“${match[2]}”`,
          '删除重复出现的连续词',
        ),
      );
    }

    for (const word of DEFAULT_DISABLED_WORDS) {
      let searchIndex = 0;
      while (searchIndex !== -1) {
        searchIndex = line.indexOf(word, searchIndex);
        if (searchIndex === -1) {
          break;
        }
        addIssue(
          issues,
          createIssue(
            'NORM-006',
            '文本质量',
            'medium',
            lineIndex + 1,
            searchIndex + 1,
            word,
            `包含禁用词“${word}”`,
            '改写为更客观、规范的表达',
          ),
        );
        searchIndex += word.length;
      }
    }

    const sentencePattern = /[^。！？!?\n]+[。！？!?]?/g;
    for (const match of line.matchAll(sentencePattern)) {
      const sentence = match[0].trim();
      if (sentence.length > 120) {
        addIssue(
          issues,
          createIssue(
            'NORM-006',
            '文本质量',
            'medium',
            lineIndex + 1,
            match.index + 1,
            sentence,
            `句子长度超过 120 个字符（当前 ${sentence.length} 个字符）`,
            '拆分成长短适中的多个句子',
          ),
        );
      }
    }
  });

  if (text.length > 0) {
    const paragraphs = text.split(/\r?\n/);
    paragraphs.forEach((line, lineIndex) => {
      const trailingSentence = line.trim();
      if (trailingSentence.length > 120 && !/[。！？!?]$/.test(trailingSentence)) {
        addIssue(
          issues,
          createIssue(
            'NORM-006',
            '文本质量',
            'medium',
            lineIndex + 1,
            1,
            trailingSentence,
            `句子长度超过 120 个字符（当前 ${trailingSentence.length} 个字符）`,
            '拆分成长短适中的多个句子',
          ),
        );
      }
    });
  }
}

async function analyzeDefaultNormativeRules(text) {
  if (typeof text !== 'string' || !text.trim()) {
    const error = new Error('text must be a non-empty string');
    error.code = 'NORMATIVE_RULES_INVALID_INPUT';
    throw error;
  }

  const lines = normalizeLines(text);
  const issues = [];

  detectSectionOrder(lines, issues);
  detectUnmatchedPairs(text, issues);
  detectRepeatedPunctuation(lines, text, issues);
  detectInvalidDates(lines, issues);
  detectReferenceNumbering(lines, issues);
  detectTextQuality(lines, text, issues);

  issues.sort((left, right) => {
    if (left.line !== right.line) {
      return left.line - right.line;
    }
    if (left.column !== right.column) {
      return left.column - right.column;
    }
    if (left.rule_id !== right.rule_id) {
      return left.rule_id.localeCompare(right.rule_id);
    }
    return left.message.localeCompare(right.message);
  });

  return { issues };
}

module.exports = {
  DEFAULT_NORMATIVE_RULES,
  analyzeDefaultNormativeRules,
};
