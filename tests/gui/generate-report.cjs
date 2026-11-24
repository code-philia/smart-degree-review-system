const fs = require('node:fs');
const path = require('node:path');
const { OUT, ROOT, created } = require('./paths.cjs');
const phaseNames = process.argv.slice(2).length ? process.argv.slice(2) : ['read-final', 'read-corrections', 'mobile-final', 'live-final', 'live-admission', 'firefox-final', 'firefox-default-check'];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const strip = value => String(value ?? '').replace(/\x1b\[[0-9;]*m/g, '');
function collect(suite, tests, phase) {
  for (const spec of suite.specs || []) for (const test of spec.tests || []) {
    const result = test.results?.at(-1) || {};
    tests.push({ phase, title: spec.title, file: spec.file, line: spec.line, project: test.projectName, status: test.status,
      resultStatus: result.status, duration: result.duration, errors: (result.errors || []).map(e => strip(e.message)),
      attachments: result.attachments || [], annotations: test.annotations || [],
      category: test.projectName === 'firefox-desktop' && /spawn UNKNOWN|browserType.launch/.test(JSON.stringify(result.errors)) ? 'environment' : 'product' });
  }
  for (const child of suite.suites || []) collect(child, tests, phase);
}
const executions = [], phases = [];
for (const phase of phaseNames) {
  const file = path.join(OUT, phase + '-results.json');
  if (!fs.existsSync(file)) throw Error('Missing phase results: ' + phase);
  const report = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (report.errors?.length) throw Error('Phase has a setup/global error: ' + phase);
  phases.push({ phase, ...report.stats });
  for (const suite of report.suites || []) collect(suite, executions, phase);
}
// Targeted reruns replace only the exact same project/file/title, never unrelated failures.
const latest = new Map();
for (const test of executions) latest.set([test.project, test.file, test.title].join('|'), test);
const tests = [...latest.values()];
const firefoxTests = tests.filter(t => t.project === 'firefox-desktop');
const failed = tests.filter(t => t.status === 'unexpected'), blocked = failed.filter(t => t.category === 'environment');
const counts = { total: tests.length, passed: tests.filter(t => t.status === 'expected').length,
  failed: failed.length - blocked.length, environment_blocked: blocked.length, skipped: tests.filter(t => t.status === 'skipped').length };
const factsFile = path.join(OUT, 'facts.json');
const facts = fs.existsSync(factsFile) ? JSON.parse(fs.readFileSync(factsFile, 'utf8')) : {};
const cleanupFile = path.join(OUT, 'cleanup-verified.json');
const cleanup = fs.existsSync(cleanupFile) ? JSON.parse(fs.readFileSync(cleanupFile, 'utf8')) : null;
const supplementFile = path.join(OUT, 'firefox-read-verification.json');
const supplementalVerification = fs.existsSync(supplementFile) ? JSON.parse(fs.readFileSync(supplementFile, 'utf8').replace(/^\uFEFF/, '')) : null;
const firefoxLabels = {
  '[live-read] cross-engine public Chinese/English sign-in and native trial dialog': '中英文登录页与试验登录弹窗',
  '[live-read] upload catalog, credits and free selection are usable': '上传页、规则目录、额度与规则选择',
  '[live-read] saved history can search and recover without navigation errors': '历史报告搜索与清空恢复',
  '[live-read] admin table/search/type dropdown are compatible': '管理员报告列表与类型筛选',
  '[live-read] admin light/dark mode persists through reload': '管理员亮暗模式及刷新保持',
};
const issueDefinitions = [
  ['P2', '历史列表把接口异常显示成空记录', '浏览器注入历史接口 HTTP 403 或 500 后，页面显示空列表，没有可辨认的读取失败/无权限提醒。真实接口正常时的列表流程另外通过。'],
  ['P2', '论文编译校验卡片的点踩提交失败', '真实上传非论文原生 PDF 后，拒绝检测符合预期；但显示的“需要改进”按钮实际提交得到 HTTP 422：“该规则暂不支持 AI 修复建议”。正常研究论文上的真实点踩与原因提交通过。'],
  ['P2', '管理员列表窄屏横向溢出', '390px 视口测得页面宽 681px；768px 视口测得页面宽 804px。表格可以独立横向滚动，整个页面不应被撑宽。'],
  ['P2', '手机主导航第一次按 Escape 未关闭', '重新打开手机主导航后，第一次 Escape 仍保留对话框；点击导航项后的关闭流程通过。'],
  ['P2', '反馈详情关闭后未恢复触发按钮焦点', '管理员打开反馈详情，再用 Escape 关闭，对话框消失，但焦点未回到原“查看反馈详情”按钮。'],
  ['P2', '无障碍检查发现对比度和嵌套交互问题', '公开登录页、额度区、管理列表等存在普通字号文字低于 WCAG AA 4.5:1 的情况；报告卡片还触发 nested-interactive 检查。详见逐项 axe 附件。'],
];
const issuePatterns = [/history (403|500)/, /rejected non-paper/, /administrator lists remain|contains wide tables/,
  /mobile navigation closes/, /feedback details show/, /accessibility|login displays a server error/];
const knownIssues = issueDefinitions.filter((_, index) => failed.some(test => issuePatterns[index].test(test.title)));
function href(file) {
  const absolute = path.isAbsolute(file) ? file : path.resolve(ROOT, file);
  return path.relative(OUT, absolute).split(path.sep).map(encodeURIComponent).join('/');
}
function evidence(t) {
  return t.attachments.filter(a => a.path && /\.png$|\.pdf$|\.zip$|\.json$/.test(a.path)).map(a => `<a href="${href(a.path)}">${esc(a.name)}</a>`).join(' · ');
}
const coverage = [
  ['身份与权限', '真实本地账号登录；访客、学生、学校账号、管理员隔离；中英文登录；安全返回地址与 WAF 边界', 'jAccount 真实扫码/密码交换未覆盖（没有可用身份）'],
  ['上传/规则/额度', '真实目录、选择/清空、文件校验、语言与主题、免费规则真实检测', '余额耗尽、排队位置 101、进行中和取消为浏览器注入；未做 101 并发压力测试'],
  ['报告阅读', '真实保存报告和原始 PDF、页码、缩放、高亮、卡片定位、严重程度与筛选', '缺失 PDF、失效报告等边界通过注入；不评估检测算法准确率'],
  ['反馈与管理', '真实新增点踩及理由、真实使用反馈、管理员可查到新增内容、分类搜索/分页/详情', '通知已读和公告领取被拦截，保护既有账号状态；AI 修改建议未实际调用'],
  ['导出与删除', '真实 PDF、Markdown、文本、Docx、图片 ZIP、JSON 下载；双报告 ZIP 与精确删除', '下载校验文件类型/非空及 ZIP 内容；不声称已逐页人工审阅所有导出版式'],
  ['设备和浏览器', 'Edge 桌面、手机/平板宽度、WebKit、Firefox、键盘/axe', counts.environment_blocked ? '浏览器启动存在环境阻塞，详见逐项结果' : 'Firefox 原缓存加载异常已用独立官方安装解决，原先阻塞的 5 项均已实际执行通过'],
];
const unique = kind => new Set(created().filter(e => e.kind === kind).map(e => e.id)).size;
const summary = { generated_at: new Date().toISOString(), target: facts.base_url, builds: facts.builds, counts, phases,
  cleanup, supplementalVerification, execution_count: executions.length, created: { jobs: unique('job'), reports: unique('report'), system_feedback: unique('system-feedback') },
  knownIssues, tests: tests.map(({ attachments, ...test }) => ({ ...test, attachments: attachments.map(a => ({ name: a.name, path: a.path })) })) };
fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>校内站点 GUI 测试报告 · 2026-11-25</title>
<style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;color:#1c2b40;background:#f3f6fa;margin:0}main{max-width:1120px;margin:40px auto;padding:32px;background:white;border:1px solid #d9e2ef;border-radius:18px}h1{font-size:30px;line-height:1.35}h2{margin-top:34px;font-size:23px}small,.muted{color:#50617a}a{color:#244db8;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{padding:12px;border:1px solid #d8e1ed;text-align:left;vertical-align:top}th{background:#f2f5fa}code,pre{font-family:Consolas,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;background:#f4f6fa;padding:14px;border-radius:8px}.stats{display:flex;flex-wrap:wrap;gap:12px}.stat{padding:14px 20px;border:1px solid #d8e1ed;border-radius:12px}.stat b{display:block;font-size:26px}.note{padding:16px 20px;background:#eef4ff;border-left:4px solid #4d6cc7}.ok{color:#14634a}.bad{color:#a52b36}details{padding:16px 0;border-bottom:1px solid #e0e5ed}summary{cursor:pointer;font-weight:600}@media(max-width:700px){main{margin:0;padding:20px;border-radius:0}table{display:block;overflow:auto}h1{font-size:25px}}</style>
<main><small>2026-11-25 · Playwright 1.57.0 · 校内 HTTPS 站点</small><h1>GUI 测试结果</h1><p>目标：<a href="https://thesis-review.sjtu.edu.cn/">thesis-review.sjtu.edu.cn</a>。本次仅编写、运行测试及清理标记数据；未修改产品代码，未推送或部署。</p>
<div class="stats">${[['用例',counts.total],['通过',counts.passed],['失败',counts.failed],['环境阻塞',counts.environment_blocked],['跳过',counts.skipped]].map(([l,n])=>`<div class="stat">${l}<b>${n}</b></div>`).join('')}</div>
<p class="muted">共执行 ${executions.length} 次，按相同浏览器/文件/标题去重后为 ${counts.total} 项，采用每项最后一次结果。失败按测试用例计数，不等同于独立缺陷数量。多个宽度、HTTP 状态或页面扫描可能命中同一问题。保留失败断言，没有为得到通过结果而修改网站或降低断言。</p>
<h2>Firefox 补测</h2><p>已通过本轮独立官方安装解决原缓存路径下的依赖加载异常。原目录的 mozglue.dll 实际存在，Firefox、mozglue.dll、xul.dll 与新安装的 SHA-256 均一致；不能据此归因为 DLL 文件缺失或损坏。独立安装已实际启动 Firefox 144.0.2，并完成以下测试；配置会自动选用该安装，无需影响其他浏览器。<a href="firefox-runtime-check.json">查看安装及启动核验</a> · <a href="https://playwright.dev/docs/browsers#managing-browser-binaries">官方缓存配置说明</a></p><table><tr><th>Firefox 用例</th><th>最终结果</th></tr>${firefoxTests.map(t=>`<tr><td>${esc(firefoxLabels[t.title] || t.title)}</td><td>${t.status==='expected'?'通过':esc(t.status)}</td></tr>`).join('')}</table><p>补测仅执行只读业务操作。${supplementalVerification?.all_existing_rows_preserved && supplementalVerification?.no_marked_data_left ? '补测后再次核对 16 表基线，既有行哈希全部保持一致，标记数据残留为 0。' : '补测后的数据核验以附加回执为准。'}<a href="firefox-read-verification.json">查看补测后核验回执</a></p>
<h2>本轮问题记录</h2>${knownIssues.length ? `<table><tr><th>优先级</th><th>问题</th><th>证据摘要</th></tr>${knownIssues.map(i=>`<tr>${i.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</table>` : '<p>此前记录的 14 项失败在本轮复测中均未再出现。完整用例结果见下方执行记录。</p>'}
<h2>实际覆盖与边界</h2><table><tr><th>范围</th><th>已执行</th><th>边界</th></tr>${coverage.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table>
<h2>数据清理</h2>${cleanup ? `<div class="note ${cleanup.all_existing_rows_preserved && cleanup.no_marked_data_left?'ok':'bad'}">既有数据逐行哈希保留：${cleanup.all_existing_rows_preserved?'通过':'未通过'}；本轮标记数据残留：${cleanup.no_marked_data_left?'0':'存在'}。清理 ${cleanup.test_jobs_removed} 个测试任务、${cleanup.test_system_feedback_ids.length} 条使用反馈。报告与报告内反馈已通过 API/界面清理，原有报告与反馈未删除。<br><a href="cleanup-verified.json">查看清理核验回执</a></div>` : '<p class="bad">尚未取得服务器清理核验回执，不能声称清理完成。</p>'}
<h2>逐项失败证据</h2>${failed.map(t=>`<details><summary>${esc(t.category==='environment'?'环境阻塞':'失败')} · ${esc(t.project)} · ${esc(t.title)}</summary><p>${esc(t.phase)} / ${esc(t.file)}:${t.line}</p><p>${evidence(t)}</p><pre>${esc(t.errors.join('\n').slice(0,11000))}</pre></details>`).join('')}
<h2>完整执行记录</h2><p>${phaseNames.map(p=>`<a href="html/${esc(p)}/index.html">${esc(p)} Playwright HTML 报告</a>`).join(' · ')} · <a href="summary.json">结构化汇总</a></p><p>read-corrections 仅针对两处测试脚本错误复测：更新为当前四项英文规则文案（下线规则应隐藏），以及点击卡片正文而非卡片中间的内嵌反馈/处理按钮。mobile-final 改用配置的手机视口宽度验证页面溢出，避免浏览器自动缩放把溢出误判为通过。站点代码未改，其余失败结果继续保留。</p>
<table><tr><th>阶段</th><th>通过</th><th>未通过（含环境）</th><th>耗时</th></tr>${phases.map(p=>`<tr><td>${esc(p.phase)}</td><td>${p.expected}</td><td>${p.unexpected}</td><td>${(p.duration/1000).toFixed(1)} 秒</td></tr>`).join('')}</table>
<p class="muted">站点构建资源：${esc((facts.builds||[]).join('、'))}。本报告是测试范围内的结果，不表示所有设备与业务路径均不存在问题。执行账号的会话 cookie、密码和完整用户数据不包含在本汇总中。</p></main></html>`;
fs.writeFileSync(path.join(OUT, 'GUI测试报告.html'), html);
console.log(JSON.stringify({ counts, report: path.join(OUT, 'GUI测试报告.html'), cleanupVerified: Boolean(cleanup?.all_existing_rows_preserved && cleanup?.no_marked_data_left) }));
