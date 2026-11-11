import legacy from './legacy-copy.json';
import { exportLabels } from '../utils/reportExport/labels';
import {REVIEW_COPY,reviewPatterns} from './review-copy';
import { SUPPLEMENTAL_COPY } from './supplemental-copy';
import {RULE_COPY} from './rule-copy';
export const COPY={...SUPPLEMENTAL_COPY,...exportLabels,...legacy,
 '使用反馈':'Feedback',
 '预':'P','中文':'中文','Language / 语言':'Language / 语言',
 '检查参考文献是否在正文、附录或图表题等全文位置被引用；发现需人工复核。':'Check whether each reference is cited in the text, appendices, captions or notes. Findings require manual review.',
 '目录中的核心内容页码系统性错位':'Contents page-number alignment',
 '检查目录条目的页码与正文标题位置是否一致。':'Check that contents page numbers match the corresponding headings.',
 '检查参考文献类型标记是否符合引用格式规范。':'Check reference type identifiers against the required citation style.',
 '按国标检查论文必备组成部分，兼容空格与拆字标题。':'Check required thesis sections against national standards, allowing for spaced and split-character headings.',
 '检查中文关键词是否少于3个或多于8个':'Check whether there are fewer than 3 or more than 8 Chinese keywords.',
 '检查中文摘要中是否出现图、表、公式或参考文献等编号':'Check for figure, table, equation or reference numbers in the Chinese abstract.',
 '检查正文各章标题是否从新页开始，即章标题上方不应再有上一章内容':'Check that each chapter begins on a new page, with no content from the previous chapter above its heading.',
 '检查论文中是否存在错别字':'Check the thesis for typographical errors.',
 '检查中英文摘要内容是否语义一致':'Check whether the Chinese and English abstracts agree in substance.',
 '检查中英文正文中错误使用标点符号的情况。':'Check for punctuation used incorrectly in Chinese or English text.',
 '检查中英文关键词是否语义一致':'Check whether Chinese and English keywords match in meaning.',
 '仅展示经规范与原文复核确认的告警。':'Show only alerts confirmed against the requirements and source text.',
 '请确认论文版本及本次检测范围':'Confirm the thesis version and review scope',
 '检测说明':'About this review',
 '聚焦公式引用、文献引用与目录页码等可定位问题。上传论文后，您可自主选择已开放规则，逐项查看检测结果，并联动定位到论文原文位置。受算力资源限制，每位用户累计检测次数不超过 3 次，请提前确认论文版本、合理勾选检测规则。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议。':'The review focuses on issues that can be located in the thesis, such as equation references, citations and contents page numbers. After uploading your thesis, select the available checks, view each finding and locate it in the thesis. Due to limited computing resources, each user may run up to 3 reviews in total. Confirm your thesis version and select the relevant checks before starting. Results are advisory. The system is in pilot testing; please share suggestions through Feedback.',
 '暂无检测记录':'No reports yet','规范性检测完成之后，检测报告将展示在这里。':'Your completed compliance reports will appear here.',
 '需要改进':'Needs improvement','跳到':'Go to ','已标记为本次已处理':'Marked as resolved for this session',
 '请稍后重试；如问题持续，请检查运行记录。':'Try again later. If the issue persists, check the run logs.',
 '调整建议：':'Suggested action: ','参考文献原文':'Reference source text','正在渲染 PDF…':'Rendering PDF…',
 '取消评价':'Withdraw feedback','负面反馈原因':'Feedback reason','可选：选择原因':'Optional: choose a reason','反馈补充说明':'Additional feedback','可选补充说明':'Additional comments (optional)','提交中…':'Submitting…','提交成功':'Feedback submitted','感谢你的反馈。':'Thank you for your feedback.','知道了':'Got it',
 '论文规范性检测报告':'Thesis compliance report','导出检测报告':'Export report','选择检测报告的导出格式':'Choose a report format','文本':'Text','图片':'Images','导出':'Export',
 '检测结果仅供参考，请结合论文原文人工复核。':'Results are advisory. Check them against the thesis text.',
 '检测结果仅供参考，请结合论文原文和学校要求人工复核。':'Results are advisory. Check them against the thesis text and university requirements.',
 '检测结果仅供参考':'Advisory results','检测结果仅供参考 ·':'Advisory results ·','智慧学位 · 论文规范性检测报告':'Smart Degree · Thesis compliance report','智慧学位 · AI 评阅辅助系统':'Smart Degree · AI Review Assistant',
 '论文题目':'Thesis title','规则版本':'Rule version','当前规则':'Current checks','问题清单':'Findings','原文定位':'Source location','未提供具体页码':'No page number available','检查依据':'Basis','参考证据':'Source evidence','未提供':'Not provided','修改建议':'Suggested action',
 '未发现问题条目；请同时核对上方检测结论及未完成的规则。':'No findings were reported. Also review the conclusion and any incomplete checks.',
 '已完成':'Completed','完成':'Done','通过':'Passed','未发现问题':'No issues found','无法判定':'Inconclusive','未发现可确认问题':'No confirmed issues','发现问题':'Issues found',
 '提交前确认':'Confirm before submitting','外部模型处理授权':'External model processing consent',
 '系统正在检测中，检测完成后将通过邮件通知您':'Your review is in progress, and we will email you when your report is ready.',
 '实时检测报告':'Live review report','实时更新':'Live updates','检测进行中，新发现的问题将自动更新到报告中。完成后自动保存至历史报告。':'New findings appear as checks finish. The completed report is saved to your history.',
 '，正在检测':', checking','PDF 预览暂时无法加载，请检查网络后重试，也可打开完整 PDF。':'The PDF preview is unavailable. Check your connection and retry, or open the complete PDF.','重新加载 PDF':'Reload PDF','打开完整 PDF':'Open complete PDF',
 '严重错误':'Critical','未能检测':'Not completed','待人工复核':'Manual review needed','摘要数值型论点核验':'Numerical claims in the abstract','前置条件未全部通过，未执行逐项数值核验。':'Not all prerequisites were met; individual numerical claims were not verified.',
 '正在估算剩余时间':'Estimating time remaining','预计 1 分钟内完成':'Estimated: within 1 minute','检测进行中':'Review in progress','已停止检测，可以重新开始。':'Review stopped. You can start again.','上传完成后可停止检测':'You can stop the review after the upload completes',
 '基于历史报告增量补跑':'Resume checks from a saved report',
 '复用原 PDF 和已完成结果，只补跑新增、失败或未能判定的规则。生成新报告，原报告保持不变。':'Reuse the PDF and completed results. Run only new, failed or inconclusive checks. A new report is created and the original is retained.',
 '复用已完成结果':'Reuse completed result','本次补跑':'Run this time','新增规则':'New check','已有规则均已完成，请勾选新增规则后补跑。':'All existing checks are complete. Select additional checks to run.',
 '您的反馈将帮助我们优化论文规范性检测和 AI 修复建议':'Your feedback helps improve thesis compliance checks and AI suggestions.',
 '整体满意度（必选）':'Overall satisfaction (required)','请选择您的整体使用感受':'How was your overall experience?',
 '您希望改进哪些方面（可多选）':'What could we improve? (Select all that apply)',
 '检测准确性':'Review accuracy','AI 建议质量':'AI suggestion quality','PDF 定位':'PDF locations','系统响应速度':'Response speed','系统稳定性':'Reliability','页面设计':'Interface design',
 '补充意见（可选）':'Additional comments (optional)','欢迎分享您的使用体验或具体建议…':'Share your experience or a specific suggestion…',
 '检测结果仅供参考，反馈内容仅用于系统改进':'Results are advisory. Feedback is used only to improve the system.',
 '很不满意':'Very dissatisfied','不太满意':'Dissatisfied','一般':'Neutral','满意':'Satisfied','非常满意':'Very satisfied','请先选择满意度':'Please select a satisfaction rating','感谢反馈！':'Thank you for your feedback!',
 '条规则':'checks','规则未实现警告 1 项':'1 incomplete check','，规则未实现警告':', incomplete checks',
 '智慧学位 AI 评阅辅助系统':'Smart Degree · AI Review Assistant',
 '智慧学位AI评阅辅助系统':'Smart Degree · AI Review Assistant',
 '试点验证版 V0.9':'Pilot V0.9','试点验证版':'Pilot',
 '论文规范性检测':'Thesis compliance review','规范性检测':'Compliance review',
 '论文上传':'Upload thesis','上传论文':'Upload thesis','上传 PDF 论文，选择检测规则并生成报告。':'Upload a PDF, select the checks and generate your report.',
 '主导航':'Main navigation','主导航菜单':'Main navigation menu','切换主导航':'Toggle navigation','收起或展开主导航':'Collapse or expand navigation','当前页面':'Current page',
 '登录系统':'Sign in','退出登录':'Sign out','账户菜单':'Account menu','正在退出…':'Signing out…',
 '论文上传与检测设置':'Thesis upload and review settings','上传待审查 PDF':'Choose a thesis PDF',
 '点击或将文件拖拽至此处上传':'Click to select a file, or drag it here',
 '支持 pdf 格式（扫描版 pdf 除外），文件大小不超过 50MB；支持中英文检测':'Text-based PDF · Up to 50 MB · Chinese and English supported',
 '移除文件':'Remove file','检测规则':'Review checks','检测规则选择':'Select review checks',
 '已选择全部检测规则':'All checks selected','已选择全部可用检测规则':'All available checks selected','正在读取检测规则…':'Loading checks…','检测规则暂未加载':'Checks have not loaded yet',
 '展开选择':'Choose checks','收起选择':'Collapse checks','全选全部检测规则':'Select all checks','清空全部检测规则':'Clear all checks','重新加载':'Reload',
 '格式规范':'Formatting','内容规范':'Content','论文逻辑审查':'Claims and evidence',
 '格式规范检测规则':'Formatting checks','内容规范检测规则':'Content checks','论文逻辑审查检测规则':'Claims and evidence checks',
 '全选格式规范':'Select all formatting checks','全选内容规范':'Select all content checks','全选论文逻辑审查':'Select all claims and evidence checks',
 '清空格式规范':'Clear formatting checks','清空内容规范':'Clear content checks','清空论文逻辑审查':'Clear claims and evidence checks',
 '实验型功能':'Beta','实验性':'Beta','实验性规则':'Beta feature',
 '暂无检测规则':'No checks available','尚未选择检测规则':'No checks selected','请选择至少一项检测规则。':'Select at least one check.',
 '核心章节完整性':'Required thesis sections','核对学位论文的必备组成部分，按内容而非字面标题识别。':'Check required thesis sections by their content, rather than by exact heading text.',
 '章标题另起一页':'Chapter page breaks','检查论文各章标题是否从新页开始，即章标题上方不应有上一章内容':'Check that each chapter begins on a new page, with no content from the preceding chapter above its heading.',
 '关键词数量':'Keyword count','检查论文关键词是否少于3个或多于8个':'Check whether the thesis has fewer than 3 or more than 8 keywords.',
 '摘要图表公式文献编号':'Numbered items in the abstract','检查中英文摘要中是否出现图、表、公式或参考文献等编号':'Check for numbered references to figures, tables, equations or references in either abstract.',
 '中英文标点符号是否混用':'Mixed punctuation','检查中英文语境内错误使用标点符号的情况。':'Check for punctuation used incorrectly in Chinese or English text.',
 '中英文关键词语义对应':'Keyword correspondence','检测中英文关键词是否语义一致':'Check whether Chinese and English keywords match in meaning.',
 '中英文摘要内容一致性':'Abstract consistency','检测中英文摘要内容是否语义一致':'Check whether the Chinese and English abstracts agree in substance.',
 '正文错别字检测':'Typographical errors','检测正文中是否存在错别字':'Check the main text for typographical errors.',
 '论点论据一致性检测':'Claims and evidence','检查摘要中的含有数值的论点是否与正文论据一致。':'Check numerical claims in the abstract against evidence in the main text.',
 '正文公式引用目标缺失':'Missing equation references','检查公式引用能否找到对应的可见公式编号。':'Check that equation references have matching equation numbers.',
 '正文引文引用编号缺失':'Missing citation numbers','检查全文引用编号能否找到对应参考文献。':'Check that every citation number has a matching reference.',
 '参考文献列表中存在未被正文引用的条目':'Uncited references','检查参考文献是否在正文、附录、图表注等全文位置被引用，结果供人工复核。':'Check for references not cited in the text, appendices, captions or notes. Results require manual review.',
 '目录中的行号与正文页号系统性错位':'Contents page-number alignment','检查目录条目页码与正文标题位置是否一致。':'Check that page numbers in the contents match the corresponding headings.',
 '引用格式错误':'Reference formatting','检查参考文献类型标识是否符合引用格式规范。':'Check reference type identifiers against the required citation style.',
 '引用的外部文献不存在':'Reference existence','仅展示按规范及原文高置信确认的告警。':'Show only high-confidence alerts supported by the requirements and source text.',
 '查找已保存的检测报告，查看问题定位与修改建议。':'Find saved reports, locate findings and review suggested changes.',
 '规范性检测报告':'Compliance reports','文档名称':'Document','检测类型':'Review type','报告生成时间':'Created','检测时间':'Reviewed on',
 '搜索检测报告':'Search reports','搜索文档名称…':'Search document names…','清空搜索':'Clear search','完成管理':'Done','全选报告':'Select all reports','全选本页':'Select this page',
 '选择或取消选择本页全部报告':'Select or deselect all reports on this page',
 '部分规则检测失败':'Some checks failed','部分规则无法判定':'Some checks are inconclusive','部分规则执行失败':'Some checks failed',
 '返回历史报告':'Back to report history','下载检测报告':'Download report','检测结论':'Review summary','检测报告详情预览':'Report details',
 '本次检测范围':'Review scope','未记录检测规则，无法确认本次检测范围。':'No checks were recorded, so the review scope cannot be confirmed.',
 '规则检查通过':'Checks passed','基础检查通过':'Basic checks passed','未触发告警':'No confirmed alerts','未统计':'Unavailable','统计中…':'Counting…',
 '规则未实现警告数':'Incomplete checks','提示错误数':'Informational findings',
 '检测结果':'Findings','规则未实现警告':'Incomplete checks','未完成检测':'Incomplete','检测失败':'Failed','不适用':'Not applicable',
 '全部规则':'All checks','全部检测规则':'All checks','全部检查项':'All checks','选择检测规则':'Select a check','按规则筛选':'Filter by check','规则筛选':'Filter checks',
 '无问题':'No issues','问题总数':'Total issues','已发现':'Found','正在检测相关问题':'Checks are still running',
 '检测完成后自动更新，您可以先查看其他已完成规则的结果。':'Results update automatically. You can view completed checks now.',
 '本规则未检测出问题':'No issues found for this check','未检测出问题':'No issues found',
 '当前筛选下暂无该级别的问题。':'No findings of this severity match the current filter.',
 '基于当前规范性检测规则，证据不足的内容仍可能无法判定。':'The current checks may be inconclusive where evidence is insufficient.',
 '检测结果仅供参考。':'Results are advisory.',
 '如需使用以下规则，请按建议内容调整；如无需使用，请忽略以下内容':'If you need these checks, follow the suggested actions. Otherwise, you may disregard this section.',
 '规则提示':'Rule notice','执行异常':'Execution error','其他检测项':'Other checks','未发现疑似不存在的引用':'No potentially nonexistent references found',
 '未找到学位论文使用授权声明，请核对论文是否包含该组成部分。':'The thesis authorization statement was not found. Check whether it is included in the document.',
 '请依据学校最新论文模板补充学位论文使用授权声明，并核对签名和日期要求。':'Add the authorization statement using the latest university template, and check the signature and date requirements.',
 '第二章标题与上一章正文出现在同一页，未另起一页。':'Chapter 2 begins on the same page as the preceding chapter, rather than on a new page.',
 '请在第二章标题前插入分页符，使章节从新的一页开始。':'Insert a page break before the Chapter 2 heading so that it begins on a new page.',
 '中文关键词“语义分析”与英文关键词“machine learning”的含义不一致。':'The Chinese keyword “语义分析” and the English keyword “machine learning” do not match in meaning.',
 '请核对两种语言的关键词，使其逐项对应；“语义分析”通常对应“semantic analysis”。':'Align the keywords in both languages. The Chinese term “语义分析” normally corresponds to “semantic analysis”.',
 '已检索到该参考文献的公开记录，请结合原始来源核对书目信息。':'A public record was found for this reference. Check its bibliographic details against the original source.',
 '请依据文献原始页面核对作者、题名、年份及出版信息。':'Check the authors, title, year and publication details against the original publication page.',
 '本次引用格式核验未完成：外部检索额度不足。':'Reference formatting could not be fully verified because the external search quota was exhausted.',
 '暂无精确定位':'No exact location','标记为已处理':'Mark as resolved','取消已处理标记':'Undo resolved mark','本次页面的临时标记，刷新后不保留':'Temporary mark for this page; cleared on refresh',
 '这个问题的判断是否准确？':'Is this finding accurate?','这条修复建议是否有帮助？':'Is this suggestion helpful?',
 '误报':'False positive','定位不准':'Incorrect location','说明不清':'Unclear explanation','内容不正确':'Incorrect content','无法直接执行':'Not actionable','依据不足':'Insufficient evidence','表达不清':'Unclear wording',
 '准确':'Accurate','不准确':'Inaccurate','有帮助':'Helpful','没帮助':'Not helpful','有用':'Helpful','无用':'Not helpful','反馈原因':'Reason','补充原因':'Add a reason',
 '取消反馈':'Withdraw feedback','撤销反馈':'Withdraw feedback','反馈已保存':'Feedback saved','修改原因':'Edit reason','原因（可选）':'Reason (optional)','请选择原因':'Select a reason',
 '修改建议：':'Suggested action: ','修复建议':'Suggested changes','规则修改提示：':'Rule guidance: ',
 '尚未生成建议。':'No suggestion generated yet.','获取修复建议':'Get a suggestion','重新生成修复建议':'Regenerate suggestion','正在生成建议…':'Preparing suggestion…','可执行建议':'Actionable suggestion',
 '建议修改为：':'Suggested text: ','建议修改后的文字':'Suggested replacement text',
 '阅读工具':'Reading tools','展开阅读工具':'Expand reading tools','收起阅读工具':'Collapse reading tools','PDF 页码跳转':'Go to PDF page','PDF 页码':'PDF page','PDF 工具':'PDF tools',
 '输入 PDF 页码，按 Enter 跳转':'Enter a PDF page number and press Enter','PDF 总页数':'Total PDF pages','PDF 上一页':'Previous PDF page','PDF 下一页':'Next PDF page',
 '高亮显示':'Highlights','隐藏高亮':'Hide highlights','聚焦高亮':'Highlight selected finding','显示全部高亮':'Show all highlights','PDF 缩放':'PDF zoom','缩小 PDF':'Zoom out','放大 PDF':'Zoom in','在浏览器打开完整 PDF':'Open the complete PDF',
 '按 PDF 实际页序计数，输入页码后按 Enter 跳转。':'Use the PDF page order. Enter a page number and press Enter.',
 '文档名称：':'Document: ',
 '报告分页':'Report pagination','每页显示条数':'Rows per page','页码选择':'Page selection','跳转页码':'Go to page','前往':'Go to','页':'page','共':'Total','条':'records','条/页':'/ page','份报告':'reports','已选择':'Selected',
 '检测任务状态':'Review task status','检测进度':'Review progress','检测阶段':'Review stages','正在上传':'Uploading','排队等待':'Queued','开始检测':'Start review','检测完成':'Complete','停止检测':'Stop review','正在停止…':'Stopping…','检测已停止':'Review stopped',
 '已加入检测队列，轮到后将自动开始，无需重复提交。':'Your review is queued and will start automatically. There is no need to submit it again.',
 '后台检测已开始，正在解析论文并执行所选规则。':'The review has started. The document is being processed and the selected checks are running.',
 '正在传输论文文件，上传后将提交后台处理。':'Uploading the document before the background review begins.',
 '正在加载登录状态…':'Loading session…','正在加载历史记录…':'Loading report history…','正在加载检测报告和原文定位…':'Loading report and document locations…','正在加载 PDF…':'Loading PDF…',
 '确认并提交':'Confirm and submit','提交反馈':'Submit feedback','补充说明':'Additional comments','取消':'Cancel','保存':'Save','关闭':'Close',
 '登录页':'Sign-in page',
 '欢迎使用':'Welcome','使用 jAccount 登录':'Sign in with jAccount','交大师生可使用校内账号统一认证':'For SJTU students and staff',
 '校内账号登录':'University account sign-in','身份认证区域':'Sign-in','学位论文规范性检测':'Thesis compliance review','格式排版':'Formatting','文字表述':'Writing','语言规范':'Language',
 '上海交通大学校徽':'Shanghai Jiao Tong University emblem','网站备案信息':'Website registration','系统说明':'About this system',
 '本系统依托人工智能技术，对照国家标准与学校规范，为学位论文提供格式排版、文字表述、语言规范等自动化检测，并给出修改建议。':'This AI-assisted system checks thesis formatting, writing and language against national and university standards and suggests improvements.',
 '论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。':'Thesis data is processed within the university. Results are advisory. The system is in pilot testing; please share suggestions through Feedback.',
 '试验账号登录':'Trial account sign-in','使用已分配的试验账号继续。':'Continue with your assigned trial account.','试验账号登录表单':'Trial account sign-in form','账号':'Account','密码':'Password','输入账号':'Enter your account ID','输入密码':'Enter password','登录':'Sign in','登录中…':'Signing in…',
};
Object.assign(COPY,REVIEW_COPY,RULE_COPY);
const plural=(n,s,p=s+'s')=>Number(n)===1?s:p;
const SECTION_NAMES={ '摘要':'abstract', '中文摘要':'Chinese abstract', '英文摘要（Abstract）':'English abstract (Abstract)', '关键词':'keywords', '目录':'contents', '引言':'introduction', '主体':'main text', '结论':'conclusion', '参考文献':'references' };
const punctuationNames={ '冒号':'colon', '逗号':'comma', '分号':'semicolon', '句号':'full stop', '问号':'question mark', '感叹号':'exclamation mark' };
const patterns=[
 [/^目录页码 (\d+) 与正文实际页码 (\d+) 不一致$/,(_,shown,actual)=>`The table of contents lists page ${shown}, but the corresponding text is on page ${actual}.`],
 [/^“([\s\S]+)”\s*中误用了(中文|英文)(冒号|逗号|分号|句号|问号|感叹号)\s*“([^”]+)”\s*，\s*应使用(中文|英文)\3\s*“([^”]+)”\s*。$/,(_,source,from,kind,wrong,to,right)=>`In “${source}”, ${from==='中文'?'a Chinese':'an English'} ${punctuationNames[kind]} “${wrong}” is used instead of ${to==='中文'?'a Chinese':'an English'} ${punctuationNames[kind]} “${right}”.`],
 [/^第 (\d+) 页审查高亮$/,(_,page)=>`Review highlights on page ${page}`],
 [/^定位审查问题：([\s\S]*)$/,(_,excerpt)=>`Locate review finding: ${excerpt}`],
 [/^(.+)：定位第 (\d+) 页$/,(_,label,page)=>`${staticEnglish(label)}: Locate page ${page}`],
 [/^编辑证据：([\s\S]*)$/,(_,source)=>`Edit evidence: ${source}`],
 [/^请(补全|补齐)或核对([^，\n]+)，确认内容完整且可读取后重新检测。$/,(_,action,sections)=>`${action==='补全'?'Complete':'Add'} or check the following sections: ${sections.split('、').map(section=>SECTION_NAMES[section]??section).join(', ')}. Make sure the content is complete and readable, then run the review again.`],
 [/^共核验 (\d+) 项论点$/,(_,n)=>`${n} ${Number(n)===1?'claim':'claims'} checked`],
 [/^论点 (\d+)$/,(_,n)=>`Claim ${n}`],
 [/^第 (\d+) 页 · 查看原文$/,(_,n)=>`Page ${n} · View source`],
 [/^检索提示：未在 SerpAPI 中查到（(\d+) 条）$/,(_,n)=>`Search notice: ${n} ${Number(n)===1?'reference was':'references were'} not found in SerpAPI`],
 [/^证据不足或运行异常：(\d+) 项$/,(_,n)=>`Insufficient evidence or execution errors: ${n}`],
 ...reviewPatterns(value=>translateEnglish(value)),
 [/^正在上传，(\d+)%$/,(_,n)=>`Uploading, ${n}%`],
 [/^发现 (\d+) 条疑似不存在的引用，请逐条人工复核。$/,(_,n)=>`${n} references require manual verification of their existence.`],
 [/^发现 (\d+) 项问题，请逐项核对。$/,(_,n)=>`${n} ${plural(n,'finding')}. Review each item individually.`],
 [/^(\d+) 星$/,(_,n)=>`${n} ${plural(n,'star')}`],[/^(\d+) 星 · (.+)$/,(_,n,label)=>`${n} ${plural(n,'star')} · ${translateEnglish(label)}`],
 [/^开始增量检测（(\d+) 项）$/,(_,n)=>`Run ${n} ${plural(n,'check')}`],[/^预计还需约 (\d+) 分钟$/,(_,n)=>`About ${n} ${plural(n,'minute')} remaining`],
 [/^导出 (.+)$/,(_,format)=>`Export ${translateEnglish(format)}`],[/^已生成 (.+)$/,(_,name)=>`Created ${name}`],
 [/^正在生成第 (\d+) \/ (\d+) 页$/,(_,n,total)=>`Generating page ${n} of ${total}`],
 [/^(严重|警告|提示) (\d+) 处$/,(_,kind,n)=>`${n} ${kind==='严重'?'critical':kind==='警告'?'warning':'informational'} findings`],
 [/^规则未实现警告 (\d+) 项$/,(_,n)=>`${n} incomplete checks`],
 [/^(\d+) 条规则$/,(_,n)=>`${n} ${plural(n,'check')}`],
 [/^，已发现 (\d+) 处问题，规则未实现警告$/,(_,n)=>`, ${n} findings, incomplete checks`],
 [/^，问题总数 (\d+) 处(.*)$/,(_,n,tail)=>`, ${translateEnglish('问题总数 '+n+' 处'+tail)}`],
 [/^已选择 (\d+) 项检测规则$/,(_,n)=>`${n} checks selected`],
 [/^已选择 (\d+) 项规则(.*)$/,(_,n,tail)=>`${n} ${plural(n,'check')} selected${tail?tail.replace(/ · 自动检查 (\d+) 项/,(_,m)=>` · ${m} automatic ${plural(m,'check')}`):''}`],
 [/^(\d+) 项问题$/,(_,n)=>`${n} findings`],[/^错误总数：(\d+)$/,(_,n)=>`Issues: ${n}`],
 [/^(\d+) 条\/页$/,(_,n)=>`${n} / page`],[/^第 (\d+) 页$/,(_,n)=>`Page ${n}`],[/^第 (\d+) \/ (\d+) 页$/,(_,n,total)=>`Page ${n} of ${total}`],
 [/^当前筛选未发现(严重|警告|提示)级别的问题$/,(_,s)=>`No ${s==='严重'?'critical':s==='警告'?'warning':'informational'} findings match this filter`],
 [/^PDF 第 (\d+) 页$/,(_,n)=>`PDF page ${n}`],[/^PDF 第 (.+) 页$/,(_,n)=>`PDF pages ${n}`],
 [/^跳到 ?(.+)$/,(_,page)=>`Go to ${translateEnglish(page)}`],
 [/^共 (\d+) 条，显示第 (\d+)–(\d+) 条$/,(_,n,a,b)=>`${a}–${b} of ${n} ${plural(n,'report')}`],
 [/^共 (\d+) 条，匹配 (\d+) 条，显示第 (\d+)–(\d+) 条$/,(_,n,m,a,b)=>`${a}–${b} of ${m} ${plural(m,'match','matches')} (${n} ${plural(n,'report')})`],
 [/^匹配 (\d+) 份$/,(_,n)=>`${n} ${plural(n,'match','matches')}`],[/^，匹配 (\d+) 条$/,(_,n)=>`, ${n} ${plural(n,'match','matches')}`],
 [/^选择报告：(.+)$/,(_,name)=>`Select report: ${name}`],[/^删除选中（(\d+)）$/,(_,n)=>`Delete selected (${n})`],
 [/^输入 1–(\d+)，按 Enter 或移出输入框跳转$/,(_,n)=>`Enter a page from 1–${n}; press Enter or leave the field to go`],
 [/^已完成 (\d+) \/ (\d+) 项规则，正在保存报告。$/,(_,n,total)=>`${Number(total)===1?`Checks complete: ${n} / ${total}`:`${n} of ${total} checks complete`}. Saving the report.`],
 [/^后台检测已开始，已完成 (\d+) \/ (\d+) 项规则。$/,(_,n,total)=>`Review in progress. ${Number(total)===1?`Checks complete: ${n} / ${total}`:`${n} of ${total} checks complete`}.`],
 [/^规则完成进度，(\d+) \/ (\d+) 项，(\d+)%$/,(_,n,total,p)=>`${Number(total)===1?`Checks complete: ${n} / ${total}`:`${n} of ${total} checks complete`}, ${p}%`],
 [/^问题总数 (\d+) 处(.*)$/,(_,n,tail)=>`${n} ${plural(n,'finding')}${tail.replace(/，严重 (\d+) 处/,', $1 critical').replace(/，警告 (\d+) 处/,(_,m)=>`, ${m} ${plural(m,'warning')}`).replace(/，提示 (\d+) 处/,', $1 informational')}`],
 [/^正在检测 (\d+) 条规则$/,(_,n)=>`${n} checks running`],
 [/^(当前报告|该规则)共发现 (\d+) (?:处|项)问题，分布在其他级别(或规则未实现警告)?。$/,(_,scope,n,verification)=>`${scope==='该规则'?'This check':'This report'} has ${n} ${plural(n,'finding')} under other severities${verification?' or Verification warnings':''}.`],
];

// Presentation state only. Canonical report data never enters localStorage.
const STORAGE_KEY='sjtu-ui-locale';
let locale='zh';try{locale=localStorage.getItem(STORAGE_KEY)==='en'?'en':'zh';}catch{}
const listeners=new Set();
let version=0;
let dynamic=new Map();
const MAX_ENTRIES=3000, MAX_CHARS=2000000;
export const missingCopy=new Set();
export const getLocale=()=>locale;
export const getPresentationRevision=()=>`${locale}:${version}`;
export const subscribe=listener=>{listeners.add(listener);return()=>listeners.delete(listener);};
const emit=()=>{version++;for(const listener of listeners)listener();};
export function localizeDocument(){
 if(typeof document==='undefined')return;
 document.documentElement.lang=locale==='en'?'en':'zh-CN';
 document.title=locale==='en'?'Smart Degree · AI Review Assistant':'智慧学位 · AI 评阅辅助系统';
}
export function setLocale(value){
 locale=value==='en'?'en':'zh';localizeDocument();
 try{localStorage.setItem(STORAGE_KEY,locale);}catch{}
 emit();
}
function staticEnglish(value){
 const trim=value.trim();if(!trim)return value;
 let result=COPY[trim];
 if(result==null)for(const [pattern,replace]of patterns)if(pattern.test(trim)){result=trim.replace(pattern,replace);break;}
 if(result==null)return value;
 return value.slice(0,value.indexOf(trim))+result+value.slice(value.indexOf(trim)+trim.length);
}
// Called by reviewed anchored templates; never substring-replace arbitrary prose.
function translateEnglish(value){return staticEnglish(value);}
export function translateStatic(value,language=getLocale()) {return language==='en'&&typeof value==='string'?staticEnglish(value):value;}
export function getTranslation(value){return dynamic.get(value);}
function recognized(value,mapping){return typeof value!=='string'||!/[\u4e00-\u9fff]/.test(value)||mapping.has(value)||staticEnglish(value)!==value;}
export function hasTranslation(value,language='en'){return language!=='en'||recognized(value,dynamic);}
export function translate(value,language=getLocale()){
 if(language!=='en'||typeof value!=='string')return value;
 const approved=staticEnglish(value);
 return approved!==value?approved:dynamic.get(value)??value;
}
export function createTranslator(language=getLocale()){
 const snapshot=new Map(dynamic);
 const translator=value=>language==='en'&&typeof value==='string'?(staticEnglish(value)!==value?staticEnglish(value):snapshot.get(value)??value):value;
 translator.has=value=>language!=='en'||recognized(value,snapshot);
 return translator;
}
export function addTranslations(values){
 let changed=false;
 for(const [source,english]of Object.entries(values||{}))if(typeof english==='string'&&english.trim()&&source.length<=20000&&english.length<=40000){
  dynamic.delete(source);dynamic.set(source,english);changed=true;
 }
 let chars=Array.from(dynamic).reduce((sum,[a,b])=>sum+a.length+b.length,0);
 while(dynamic.size>MAX_ENTRIES||chars>MAX_CHARS){const [a,b]=dynamic.entries().next().value;dynamic.delete(a);chars-=a.length+b.length;}
 if(changed)emit();
}
export function clearTranslations(){dynamic.clear();emit();}
Object.assign(COPY,{
 '中文摘要原句':'Original sentence from the Chinese abstract','英文摘要原句':'Original sentence from the English abstract','中文摘要':'Chinese abstract','英文摘要':'English abstract',
 '缺少完整的方括号文献类型标记':'The bracketed reference type code is missing or incomplete.',
 '报告加载失败':'Failed to load report','反馈保存失败':'Failed to save feedback','反馈取消失败':'Failed to withdraw feedback',
 '请重新打开检测报告后提交反馈':'Reopen the report before submitting feedback','请重新加载修复建议后提交反馈':'Reload the suggestion before submitting feedback',
 '当前 AI 服务请求较多，请稍后重试':'The AI service is busy. Please try again later.','修复建议暂不可用':'Suggestions are temporarily unavailable',
 'jAccount 登录已过期，请重新登录。':'Your jAccount sign-in expired. Please sign in again.',
 'jAccount 登录暂未完成，请重试。':'jAccount sign-in was not completed. Please try again.',
 '已取消 jAccount 登录，可重新登录。':'jAccount sign-in was cancelled. You can sign in again.',
 'jAccount 登录暂不可用，请稍后重试或联系系统管理员。':'jAccount sign-in is unavailable. Try again later or contact the administrator.',
 '此账号无法通过 jAccount 登录，请联系系统管理员。':'This account cannot sign in with jAccount. Contact the administrator.',
 'Translation is not ready. Please retry before exporting.':'Translation is not ready. Please retry before exporting.'
});
if(typeof window!=='undefined')window.addEventListener('storage',event=>{if(event.key===STORAGE_KEY){locale=event.newValue==='en'?'en':'zh';localizeDocument();emit();}});
localizeDocument();
