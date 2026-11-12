# 学生端操作手册 / Student user guides

本目录维护已确认的中英文学生手册。中文、英文各为一个独立 PDF，分别从第 1 页编号，有自己的目录、书签和内部跳转。

- [中文手册（29 页）](../../frontend/public/manuals/智慧学位AI评阅辅助系统-学生端操作手册.pdf)
- [English guide (30 pages)](<../../frontend/public/manuals/Smart Degree · AI Review Assistant - Student User Guide.pdf>)

网站发布后，两个文件位于 `/manuals/` 下。保留现有中英文文件名；含空格和中文的 URL 应按 UTF-8 编码，完整下载路径见 [manifest.json](manifest.json)。源码目录不会作为网站静态文件公开。

## 源码与配图

- `latex/student-guide-zh.tex`、`student-guide-en.tex`：可直接编译的两份 XeLaTeX 源码。
- `latex/build_manual.py`：从三个 JSON 正文文件生成指定语言的源码，仅使用 Python 标准库。
- `latex/manual-content.json`、`report-modules.json`、`extra-modules.json`：中英文正文。
- `latex/guide-assets/`：用户已确认的 46 张对应语言截图及校徽；`asset-manifest.json` 记录配图 SHA256。
- `manifest.json`：已交付 PDF 的文件名、语言、页数、SHA256 和发布路径。

只收录手册使用的已遮蔽配图，不收录未遮蔽原图、真实用户论文或报告、私有归档、运行配置、账号密码和 API 密钥。不得改写、重排或移动用户已确认的 PixPin 文字、编号、红框和箭头；内容遮蔽与裁剪必须避开标注。

## 构建环境

使用 XeLaTeX 和常规 TeX Live 宏包。所需字体为 DejaVu Serif、DejaVu Sans、Noto Serif CJK SC、Noto Sans CJK SC、Noto Sans Mono CJK SC。无需 Overleaf 或图片生成服务。

从仓库根目录进入源码目录，修改 JSON 后重新生成两种语言的源码：

```sh
cd docs/student-guide/latex
python3 build_manual.py --language zh
python3 build_manual.py --language en
```

每份执行两次，以更新目录和跳转页码：

```sh
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error student-guide-zh.tex
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error student-guide-zh.tex
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error student-guide-en.tex
xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error student-guide-en.tex
```

若只修改排版，也须同步修改生成器，避免下次生成时丢失改动。编译产物与日志在本目录忽略；正式 PDF 必须更新到 `frontend/public/manuals/`：

```sh
cp student-guide-zh.pdf '../../../frontend/public/manuals/智慧学位AI评阅辅助系统-学生端操作手册.pdf'
cp student-guide-en.pdf '../../../frontend/public/manuals/Smart Degree · AI Review Assistant - Student User Guide.pdf'
```

## 更新与发布检查

1. 对照当前网站核实文案、规则、徽标颜色、额度、取消及语言行为，同时更新对应中英文说明。
2. 保留学生正式入口 `https://thesis-review.sjtu.edu.cn`；文件名不附加“中文版/英文版”，中文文件用中文名，英文文件用英文名。
3. 检查每种语言的截图与图文对应关系。截图与 PixPin 标注已由用户确认，改动前需明确取得授权。
4. 编译后渲染检查所有变更页，核对目录、页码、链接、文字与图标对齐、无缺字或溢出。不要为排版压缩字号或行距。
5. 更新正式 PDF 和 `manifest.json` 中的页数、SHA256；源码、配图及 PDF 应在同一提交中维护。重新编译的时间元数据可能改变 PDF 哈希，因此以本次确认的成品文件计算 SHA256。
6. 按已有发布流程构建前端，核对 `/manuals/` 两个下载返回 `application/pdf` 且文件 SHA256 与清单一致。源码变更不需要运行论文检测或发送邮件。

手册维护不修改系统原有检测逻辑。学生上传要求为学位论文的文字版 PDF，不能是非论文文件、扫描版或纯图片 PDF，且不超过 50 MB；这类要求以网站实际行为为准。
