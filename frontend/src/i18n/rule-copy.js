/* Translate the checks by their actual scope. Chinese keys remain unchanged. */
export const RULE_ENGLISH = [
  {
    id:'sjtu_rule_18', title:'Equation cross-references',
    description:'Check that each equation cited in the text has a matching visible equation number.',
    titles:['正文公式引用目标缺失'],
    descriptions:['检查公式引用能否找到对应的可见公式编号。'],
  },
  {
    id:'sjtu_rule_22', title:'Citation matching',
    description:'Check that each numbered citation in the document matches an entry in the reference list.',
    titles:['正文引文引用编号缺失'],
    descriptions:['检查全文引用编号能否找到对应参考文献。'],
  },
  {
    id:'sjtu_rule_24', title:'Uncited references',
    description:'Identify reference-list entries that are not cited anywhere in the document. Review flagged entries manually.',
    titles:['参考文献列表中存在未被正文引用的条目'],
    descriptions:['检查参考文献是否在正文、附录或图表题等全文位置被引用；发现需人工复核。','检查参考文献是否在正文、附录、图表注等全文位置被引用，结果供人工复核。'],
  },
  {
    id:'sjtu_rule_28', title:'Contents page numbers',
    description:'Check contents page numbers against the pages where the corresponding headings appear in the main text.',
    titles:['目录中的核心内容页码系统性错位','目录中的行号与正文页号系统性错位'],
    descriptions:['检查目录条目的页码与正文标题位置是否一致。','检查目录条目页码与正文标题位置是否一致。'],
  },
  {
    id:'sjtu_rule_31', title:'Reference type codes',
    description:'Check for missing or invalid reference type codes, such as [J] for journal articles and [C] for conference papers, where required by the reference style.',
    titles:['引用格式错误'],
    descriptions:['检查参考文献类型标记是否符合引用格式规范。'],
  },
  {
    id:'sjtu_rule_32', title:'Reference verification',
    description:'Look up cited publications to assess whether they exist. Suspected nonexistent references need manual review; incomplete searches are reported separately.',
    titles:['引用的外部文献不存在'],
    descriptions:['仅展示经规范与原文复核确认的告警。'],
  },
  {
    id:'typo_detection_check', title:'Chinese character errors',
    description:'Find clear Chinese character errors in the main text. Grammar, style and English spelling are outside this check.',
    titles:['正文错别字检测'],
    descriptions:['检查论文中是否存在错别字','检测正文中是否存在错别字'],
  },
  {
    id:'bilingual_keywords_correspondence_check', title:'Bilingual keyword match',
    description:'Check that the Chinese and English keyword lists express the same concepts and correspond to each other.',
    titles:['中英文关键词语义对应'],
    descriptions:['检查中英文关键词是否语义一致','检测中英文关键词是否语义一致'],
  },
  {
    id:'bilingual_abstract_consistency_check', title:'Bilingual abstract agreement',
    description:'Compare the Chinese and English abstracts for substantive differences in the research topic, methods, results and conclusions.',
    titles:['中英文摘要内容一致性'],
    descriptions:['检查中英文摘要内容是否语义一致','检测中英文摘要内容是否语义一致'],
  },
  {
    id:'required_section_completeness_check', title:'Required thesis sections',
    description:'Check the required thesis sections against national standards, allowing for spaces between heading characters and headings split across text fragments.',
    titles:['核心章节完整性'],
    descriptions:['按国标检查论文必备组成部分，兼容空格与拆字标题。','核对学位论文的必备组成部分，按内容而非字面标题识别。'],
  },
  {
    id:'chinese_english_symbol_mix_check', title:'Chinese/English punctuation',
    description:'Find English punctuation used incorrectly in Chinese prose, or Chinese punctuation used incorrectly in English prose.',
    titles:['中英文标点符号是否混用'],
    descriptions:['检查中英文正文中错误使用标点符号的情况。','检查中英文语境内错误使用标点符号的情况。'],
  },
  {
    id:'keyword_count_check', title:'Chinese keyword count',
    description:'Check that the Chinese keyword list contains 3–8 keywords.',
    titles:['关键词数量'],
    descriptions:['检查中文关键词是否少于3个或多于8个','检查论文关键词是否少于3个或多于8个'],
  },
  {
    id:'abstract_object_number_check', title:'Abstract cross-references',
    description:'Flag figure, table and equation numbers and numbered citations in the Chinese and English abstracts.',
    titles:['摘要图表公式文献编号'],
    descriptions:['检查中文摘要中是否出现图、表、公式或参考文献等编号','检查中英文摘要中是否出现图、表、公式或参考文献等编号'],
  },
  {
    id:'chapter_new_page_check', title:'Chapter page breaks',
    description:'Check that each chapter starts on a new page, with no text from the previous chapter above its heading.',
    titles:['章标题另起一页'],
    descriptions:['检查正文各章标题是否从新页开始，即章标题上方不应再有上一章内容','检查论文各章标题是否从新页开始，即章标题上方不应有上一章内容'],
  },
  {
    id:'abstract_numeric_consistency_check', title:'Numerical claim verification',
    description:'Check numerical claims in the abstract against the experimental results in the corresponding research chapters.',
    titles:['摘要数值声明与实验结果一致性','论点论据一致性检测'],
    descriptions:['检查摘要中的数值型研究声明是否与对应研究章节下实验子章节的结果一致。','检查摘要中的含有数值的论点是否与正文论据一致。'],
  },
];
export const RULE_COPY={...Object.fromEntries(RULE_ENGLISH.flatMap(rule=>[
  ...rule.titles.map(key=>[key,rule.title]),
  ...rule.descriptions.map(key=>[key,rule.description]),
])),
 '核对学位论文的必备组成部分，按内容而非字面标题识别。':'Check the required thesis sections by content rather than exact heading wording.',
};
