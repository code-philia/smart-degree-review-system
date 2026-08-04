const ALLOWED_INNOVATION_SCORING_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];
const MAX_INNOVATION_SCORING_JSON_BYTES = '32kb';

const INNOVATION_SCORE_DIMENSIONS = [
  { key: 'research_topic', label: '研究选题' },
  { key: 'research_method', label: '研究方法' },
  { key: 'research_content', label: '研究内容' },
  { key: 'research_conclusion', label: '研究结论' },
  { key: 'application_value', label: '应用价值' },
];

const INNOVATION_SCORE_WEIGHTS = {
  doctoral: {
    research_topic: 0.25,
    research_method: 0.25,
    research_content: 0.2,
    research_conclusion: 0.2,
    application_value: 0.1,
  },
  master: {
    research_topic: 0.2,
    research_method: 0.2,
    research_content: 0.25,
    research_conclusion: 0.2,
    application_value: 0.15,
  },
};

function calculateInnovationScore() {
  const error = new Error('创新性评分模型服务待实现');
  error.code = 'INNOVATION_SCORING_SERVICE_NOT_IMPLEMENTED';
  throw error;
}

module.exports = {
  ALLOWED_INNOVATION_SCORING_ROLES,
  INNOVATION_SCORE_DIMENSIONS,
  INNOVATION_SCORE_WEIGHTS,
  MAX_INNOVATION_SCORING_JSON_BYTES,
  calculateInnovationScore,
};
