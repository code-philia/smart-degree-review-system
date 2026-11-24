# 校内站点 Playwright GUI 测试

默认目标为 <https://thesis-review.sjtu.edu.cn/>；`GUI_BASE_URL` 也允许外网 <http://121.36.247.138:3000>。本测试工具只运行测试，不修改或部署网站。只有显式设置 `GUI_ALLOW_LOCAL=1` 才允许环回地址预览。

## 本次覆盖

- 中文/英文公开登录、试验账号真实登录、管理员真实登录、访客/普通用户/管理员权限边界。
- 上传与规则选择、免费/付费规则展示、额度环及余额、亮暗模式、语言与设置、公告、通知、反馈表单。
- 历史报告搜索、筛选、分页、全选/清空、导出、删除确认；管理员全量报告与反馈分类搜索及详情。
- 真实保存报告和真实 PDF：页码校验、跳转、缩放、高亮开关、卡片原文定位。
- 标记副本真实检测、真实点踩和意见提交、管理员可见性、六种单报告导出、双报告批量导出与删除。
- 通过浏览器拦截验证排队、运行中/取消、额度不足、无记录、网络失败、失效会话、403/404/410/500 等状态。
- 桌面、平板、手机宽度，Edge/Chromium、WebKit、Firefox，键盘焦点和 axe WCAG 检查。

`[live-read]` 读取真实站点；`[live-write]` 只操作本轮标记数据；`[injected]` 是浏览器侧模拟响应，不代表真实后台已承受对应负载。各用例的网络边界附在 HTML 报告中。Firefox 原缓存目录的加载异常已通过独立安装解决，原先阻塞的 5 项已补测通过。

## 安装与运行（PowerShell）

在仓库根目录执行：

```powershell
npm ci --prefix tests/gui --ignore-scripts --no-audit --no-fund
node tests/gui/node_modules/playwright/cli.js install webkit
# Edge 使用系统已安装的 Microsoft Edge。
# 使用已分配的本地试验账号密码；不要把密码写进脚本或提交到仓库。
$env:GUI_PASSWORD = '<现有本地账号密码>'
$env:GUI_OUTPUT_DIR = (Join-Path (Get-Location) 'output/campus-gui-new-run')
node tests/gui/install-firefox.cjs
node tests/gui/audit.cjs
```

每次独立审计使用新的输出目录；同一轮重跑复用目录内的隔离登录会话，以免触发线上登录限流。脚本不会保存密码，`.auth` 中包含会话 cookie，不能上传、提交或分享。

`install-firefox.cjs` 按 [Playwright 官方缓存配置](https://playwright.dev/docs/browsers#managing-browser-binaries) 将 Firefox 安装到本轮输出目录的 `firefox-runtime`；测试配置自动选择该安装，不覆盖共享浏览器缓存，也不影响 Edge/WebKit。当前版本锁定 Playwright 1.57.0 / Firefox 144.0.2（revision 1497）。需要指定已有兼容安装时可设置 `GUI_FIREFOX_EXECUTABLE`。

## 真实写入测试

本次用户已允许创建标记报告/反馈、仅清理本次数据，并允许检测完成通知邮件。**重新执行必须确认授权仍适用于新一轮测试。**真实检测仅选择 `required_section_completeness_check` 和 `keyword_count_check`，不调用付费模型。

```powershell
$env:GUI_ALLOW_LIVE_WRITES = '1'
$env:GUI_ALLOW_EMAIL = '1'
$env:GUI_LIVE_PDF = 'C:\absolute\approved-real-research-paper.pdf'
node tests/gui/audit.cjs
```

默认缺少任一授权开关时跳过真实写入。`GUI_LIVE_PDF` 必须是获准使用的真实研究论文；仓库内 1713 字节原生 PDF 仅用于界面与非论文拒绝路径测试，不能替代真实论文。

`audit.cjs` 即使发现只读 GUI 问题，也会继续运行获准的生命周期测试，最终仍返回非零退出码。各阶段结果隔离保存，失败不会被后续阶段覆盖。也可用 Playwright `--project`、`--grep` 单独执行；`live-lifecycle --no-deps` 用于依赖阶段已完成的复测。

## 数据保护与清理

`guard.cjs` 默认阻止写入。仅放行本轮 `GUI_TEST_` 文件名、已登记报告 ID 的反馈/删除、带本轮前缀的使用反馈，以及不修改报告的导出。公告领取、通知已读、英文报告模型翻译会被拦截，保留原账号状态；这些被拦截的功能须按模拟覆盖解释。

`created.jsonl` 登记本轮任务、报告和反馈。Playwright teardown 按 ID 和文件名前缀双重检查，再通过报告 API 清理。任务记录、使用反馈及衍生文件由 `server-data-audit.py` 清理，不执行数据库重置。

服务器侧操作由有 SSH 权限的操作者完成：

1. 写入测试前，以独立私有目录运行 `python3 server-data-audit.py snapshot /absolute/private/task-dir`，保存既有数据逐行哈希；拒绝覆盖已有基线。
2. 写入结束并完成 API 清理后，将**同一轮** `run.json`、`created.jsonl` 上传至该目录。
3. 执行 `python3 server-data-audit.py cleanup /absolute/private/task-dir`。只清理已登记、非基线、当前前缀且已终止的测试任务/反馈，检查 PDF 路径，核对所有既有行哈希及测试前缀残留。
4. 保存 `cleanup-verified.json`。出现未登记记录、既有数据变更或残留时停止，不扩大删除范围。

本助手适配当前校内部署的服务/数据库结构，换环境须先检查路径。真实完成邮件可能已发送，清理数据不会撤回邮件。登录会话是本轮临时会话，不纳入报告内容基线。

## 证据与限制

- HTML：`output/<本轮>/html/<阶段>/index.html`；JSON：`<阶段>-results.json`；截图及下载文件：`artifacts/<阶段>/`。
- 本轮正式结果为 `read-final`、`read-corrections`、`mobile-final`、`live-final`、`live-admission`、`firefox-final` 和 `firefox-default-check`；按项目/文件/用例标题去重，采用每项最新结果。Firefox 的 5 项完整补测及不依赖临时全局环境变量的启动复测均通过；早期阻塞和探索结果仅保留追溯。
- 没有真实 jAccount 身份，不能声称完成账号密码/扫码后的真实 SSO 回跳；只验证入口、返回地址、错误状态及真实本地账号登录。
- 排队位置和余额耗尽等状态由拦截验证界面，不是 101 并发压力测试；没有实际消费付费规则 token，也没有生成真实 AI 修改建议。
- 浏览器自动化和 axe 结果不能代替所有设备上的人工观感审查；列出已测矩阵，不宣称不存在未覆盖问题。
