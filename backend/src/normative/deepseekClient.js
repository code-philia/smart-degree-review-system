const DEEPSEEK_API_URL = 'https://api.deepseek.com/chat/completions';
const DEEPSEEK_MODEL = 'deepseek-chat';
const REQUEST_TIMEOUT_MS = 30000;

const LEVEL_INSTRUCTIONS = Object.freeze({
  basic: '仅修正错别字、标点符号和明显语病，尽量保留原文的表达和结构，不做额外改写。',
  standard: '在基础校准之外，优化用词和句子流畅度，使表达更学术、准确，但保留原意和整体结构。',
  enhanced: '在标准优化之外，对逻辑不清或过长的句子进行适当重组，使全文更严谨流畅，但不得改变原文的事实和结论。',
});

function buildSystemPrompt(level) {
  const instruction = LEVEL_INSTRUCTIONS[level] || LEVEL_INSTRUCTIONS.standard;
  return `你是一名中文学位论文润色助手。${instruction}只输出润色后的全文正文，不要添加解释、标题、markdown 标记或多余的引号。`;
}

async function polishWithDeepseek(text, level) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    throw new Error('DEEPSEEK_API_KEY not configured');
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(DEEPSEEK_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: DEEPSEEK_MODEL,
        temperature: 0.3,
        messages: [
          { role: 'system', content: buildSystemPrompt(level) },
          { role: 'user', content: text },
        ],
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(`DeepSeek API error ${response.status}: ${detail.slice(0, 500)}`);
    }

    const data = await response.json();
    const polished = data?.choices?.[0]?.message?.content;
    if (typeof polished !== 'string' || !polished.trim()) {
      throw new Error('DeepSeek API returned empty content');
    }
    return polished.trim();
  } finally {
    clearTimeout(timeout);
  }
}

module.exports = { polishWithDeepseek };
