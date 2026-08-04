const DEFAULT_NORMATIVE_RULES = Object.freeze([
  { rule_id: 'NORM-001', category: '章节顺序', title: '摘要、关键词、引言、结论、参考文献必须按顺序出现' },
  { rule_id: 'NORM-002', category: '标点配对', title: '检查中英文圆括号、方括号、书名号和引号是否成对' },
  { rule_id: 'NORM-003', category: '重复标点', title: '报告“，，”“。。”“；；”和连续三个以上相同标点' },
  { rule_id: 'NORM-004', category: '日期格式', title: '数字日期仅接受 YYYY-MM-DD' },
  { rule_id: 'NORM-005', category: '参考文献', title: '参考文献后的非空行必须以 [1] 开始并连续递增' },
  { rule_id: 'NORM-006', category: '文本质量', title: '报告连续重复词、Tab、行尾空格、超过 120 个字符的句子以及禁用词' },
]);

async function analyzeDefaultNormativeRules(text) {
  if (typeof text !== 'string') {
    const error = new Error('text must be a string');
    error.code = 'NORMATIVE_RULES_INVALID_INPUT';
    throw error;
  }

  const error = new Error('默认规范检测规则服务尚未实现');
  error.code = 'NORMATIVE_RULES_NOT_IMPLEMENTED';
  throw error;
}

module.exports = {
  DEFAULT_NORMATIVE_RULES,
  analyzeDefaultNormativeRules,
};
