"""Build editable XeLaTeX sources for combined or standalone student guides."""
from pathlib import Path
import argparse
import json

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--language',choices=('both','zh','en'),default='both')
args=parser.parse_args()
languages=['zh','en'] if args.language=='both' else [args.language]
data=json.loads((ROOT/'manual-content.json').read_text(encoding='utf-8'))
data['sections'][1]['modules']=json.loads((ROOT/'report-modules.json').read_text(encoding='utf-8'))
data['sections'][2]['modules']=json.loads((ROOT/'extra-modules.json').read_text(encoding='utf-8'))
def esc(s):
    replacements={'\\':r'\textbackslash{}','{':r'\{','}':r'\}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    out=''.join(replacements.get(c,c) for c in str(s))
    return out.replace('https://thesis-review.sjtu.edu.cn',r'\url{https://thesis-review.sjtu.edu.cn}')
parts=[]
def emit(s):parts.append(s)
emit(r"""
\documentclass[12pt,a4paper]{article}
\usepackage[left=22mm,right=22mm,top=23mm,bottom=23mm,headheight=15pt,headsep=8mm]{geometry}
\usepackage{fontspec,xeCJK}
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}
\setCJKmainfont{Noto Serif CJK SC}
\setCJKsansfont{Noto Sans CJK SC}
\setCJKmonofont{Noto Sans Mono CJK SC}
\usepackage{graphicx,xcolor,tikz,enumitem,needspace,tabularx,array,booktabs,fancyhdr,titlesec}
\usetikzlibrary{arrows.meta,calc}
\usepackage[unicode,colorlinks=true,linkcolor=navy,urlcolor=maroon,bookmarksopen=true,bookmarksnumbered=true]{hyperref}
\definecolor{navy}{HTML}{172D46}
\definecolor{maroon}{HTML}{96364F}
\definecolor{muted}{HTML}{526276}
\definecolor{pale}{HTML}{F2F5F9}
\definecolor{rose}{HTML}{E11D48}
\definecolor{amber}{HTML}{D97706}
\definecolor{blue}{HTML}{2563EB}
\definecolor{progressink}{HTML}{1F3F63}
\definecolor{progressbg}{HTML}{F5F9FF}
\definecolor{violet}{HTML}{7C3AED}
\definecolor{green}{HTML}{059669}
\definecolor{slate}{HTML}{64748B}
\hypersetup{pdftitle={智慧学位 AI 评阅辅助系统：学生端操作手册 / Student User Guide},pdfauthor={智慧学位 AI 评阅辅助系统},pdfsubject={Chinese followed by English, illustrated student instructions}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\emergencystretch}{2em}
\AtBeginDocument{\fontsize{12}{19.5}\selectfont}
\setlist[enumerate]{leftmargin=1.8em,label=\textcolor{maroon}{\bfseries\arabic*.},itemsep=4pt,topsep=5pt,parsep=0pt}
\setlist[itemize]{leftmargin=1.5em,itemsep=4pt,topsep=5pt}
\titleformat{\section}{\sffamily\bfseries\color{navy}\fontsize{19}{25}\selectfont}{\textcolor{maroon}{\thesection}}{.7em}{}
\titleformat{\subsection}{\sffamily\bfseries\color{navy}\fontsize{15}{21}\selectfont}{\thesubsection}{.65em}{}
\titlespacing*{\section}{0pt}{0pt}{10pt}
\titlespacing*{\subsection}{0pt}{8pt}{9pt}
\newcommand{\currentlanguage}{zh}
\renewcommand{\theHsection}{\currentlanguage.\arabic{section}}
\renewcommand{\theHsubsection}{\theHsection.\arabic{subsection}}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\sffamily\fontsize{9}{12}\selectfont\color{muted}\runningtitle}
\fancyhead[R]{\sffamily\fontsize{9}{12}\selectfont\color{muted}2026.11}
\fancyfoot[C]{\sffamily\fontsize{10}{13}\selectfont\color{muted}\thepage}
\renewcommand{\headrulewidth}{.35pt}
\renewcommand{\footrulewidth}{0pt}
\newcommand{\runningtitle}{学生端操作手册}
\newcommand{\note}[1]{\par\medskip\noindent\begingroup\setlength{\fboxsep}{9pt}\colorbox{pale}{\parbox{\dimexpr\linewidth-18pt\relax}{#1}}\endgroup\par}
\newcommand{\pic}[5]{\begin{center}\includegraphics[width=#3,height=#4,keepaspectratio]{guide-assets/#1.png}\par\vspace{3pt}{\fontsize{10}{14}\selectfont\color{muted}#5}\label{fig:#1}\end{center}}
\newcommand{\circlex}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw (0,0)circle(.65);\draw(-.24,-.24)--(.24,.24)(-.24,.24)--(.24,-.24);}}
\newcommand{\triangleicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,.72)--(-.68,-.48)--(.68,-.48)--cycle;\draw(0,.3)--(0,-.08);\fill(0,-.27)circle(.05);}}
\newcommand{\infoicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,0)circle(.65);\draw(0,-.3)--(0,.08);\fill(0,.32)circle(.06);}}
\newcommand{\shieldicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,.7)--(.58,.46)--(.48,-.23)..controls(.2,-.57)..(0,-.72)..controls(-.2,-.57)..(-.48,-.23)--(-.58,.46)--cycle;\draw(0,.3)--(0,-.08);\fill(0,-.3)circle(.05);}}
\newcommand{\spinicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=1pt,sharp corners]{\draw(30:.62)arc(30:320:.62);}}
\newcommand{\alerticon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,0)circle(.65);\draw(0,.32)--(0,-.08);\fill(0,-.3)circle(.05);}}
\newcommand{\questionicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,0)circle(.65);\node[font=\sffamily\bfseries\scriptsize]at(0,0){?};}}
\newcommand{\checkicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(0,0)circle(.65);\draw(-.32,0)--(-.08,-.24)--(.35,.27);}}
\newcommand{\flaskicon}{\tikz[baseline=-.4ex,x=.65em,y=.65em,line width=.8pt,sharp corners]{\draw(-.25,.7)--(.25,.7)(-.15,.7)--(-.15,.2)--(-.63,-.56)--(.63,-.56)--(.15,.2)--(.15,.7);\draw(-.38,-.18)--(.38,-.18);}}
\newsavebox{\badgeIconBox}
\newsavebox{\badgeLabelBox}
\newlength{\badgeIconLift}
\newcommand{\badge}[4]{%
  \begingroup\color{#1}%
  \sbox{\badgeLabelBox}{\sffamily\small\color{black}#3}%
  \sbox{\badgeIconBox}{\sffamily\small#2}%
  \setlength{\badgeIconLift}{\dimexpr(\ht\badgeLabelBox-\dp\badgeLabelBox-\ht\badgeIconBox+\dp\badgeIconBox)/2\relax}%
  \tikz[baseline=-.6ex]\node[rounded corners=4pt,fill=#4,inner xsep=6pt,inner ysep=4pt,font=\sffamily\small]{\raisebox{\badgeIconLift}{\usebox{\badgeIconBox}}\hspace{4pt}\usebox{\badgeLabelBox}};%
  \endgroup}
\raggedbottom
\begin{document}
""")

def titlepage(lang):
    if lang=='zh':
        title='学生端操作手册';sys='智慧学位 AI 评阅辅助系统'
        entry='学生使用入口';date='2026 年 11 月'
    else:
        title='Student User Guide';sys='Smart Degree · AI Review Assistant'
        entry='Student access';date='November 2026'
    emit(r'\clearpage\thispagestyle{empty}\pdfbookmark[0]{'+esc(title)+'}{part-'+lang+'}')
    emit(r'\vspace*{26mm}\begingroup\centering\includegraphics[width=22mm]{guide-assets/sjtu-emblem.jpg}\par')
    emit(r'\vspace{22mm}{\sffamily\color{navy}\bfseries\fontsize{'+('24' if lang=='zh' else '22')+r'}{34}\selectfont '+esc(sys)+r'\par}')
    emit(r'\vspace{10mm}{\sffamily\color{navy}\bfseries\fontsize{32}{42}\selectfont '+esc(title)+r'\par}')
    emit(r'\vspace{15mm}{\color{maroon}\rule{.62\linewidth}{1.1pt}}\par\vspace{15mm}')
    emit(r'{\sffamily\color{muted}'+esc(entry)+r'\par}\vspace{2mm}\url{https://thesis-review.sjtu.edu.cn}\par')
    emit(r'\vfill{\color{muted}'+esc(date)+r'\par}')
    emit(r'\vspace*{7mm}\par\endgroup')

def contents(lang):
    emit(r'\clearpage\thispagestyle{plain}\section*{'+('目录' if lang=='zh' else 'Contents')+'}')
    rows=[('intro','文档介绍','About this guide'),('overview','系统概述','System overview'),
          ('basic','基本操作','Starting a review'),('reports','报告查看与管理','Reading and managing reports'),
          ('extras','辅助功能','Other features'),('faq','常见问题','Frequently asked questions'),('rules','附录：检测规则速查','Appendix: Check reference')]
    for i,(key,zh,en) in enumerate(rows):
        text=(str(i+1)+'  ' if i<6 else '')+(zh if lang=='zh' else en)
        emit(r'\noindent\hyperref['+lang+':'+key+']{'+esc(text)+r'}\dotfill\pageref{'+lang+':'+key+r'}\par\vspace{5mm}')
    links=[('upload','上传文件要求','File requirements'),('progress','停止检测','Stopping a review'),('reading','阅读工具','Reading tools'),('badges','颜色与徽标说明','Colours and badges'),('export','下载报告','Downloading reports'),('settings','语言与外观','Language and appearance')]
    emit(r'\vspace{5mm}{\sffamily\bfseries\color{navy}'+('常用操作快速定位' if lang=='zh' else 'Quick links')+r'}\par')
    for key,zh,en in links:
        emit(r'\hyperref['+lang+':'+key+']{'+esc(zh if lang=='zh' else en)+r'}\dotfill\pageref{'+lang+':'+key+r'}\par')

def intro(lang):
    emit(r'\clearpage\setcounter{section}{0}\section{'+('文档介绍' if lang=='zh' else 'About this guide')+r'}\label{'+lang+':intro}')
    zh=[
      ('编写目的','本手册帮助学生完成登录、论文提交、结果复核、报告下载与历史记录管理。按照编号步骤操作，并结合对应截图中的红框、箭头和文字定位按钮。'),
      ('适用范围','适用于智慧学位 AI 评阅辅助系统学生端。内容依据 2026 年 11 月的界面整理。请使用正式域名；后续界面局部变化时，以当前页面提示为准。'),
      ('阅读约定','图 01—23 在每种语言中分别对应同一组操作；同一流程可能合用两张图。截图中的数量、时间和账号仅用于说明操作。'),
      ('内容保护','手册不展示他人论文正文。请以本人实际报告为准，逐项核对原文。'),
      ('结果使用','系统提供辅助检查与修改建议，不代替导师、学院或学校的人工审核。请对照论文原文与学校要求逐项复核，不把“未发现问题”理解为合规证明。')]
    en=[
      ('Purpose','This guide helps students sign in, submit a thesis, review findings, download reports and manage saved records. Follow the numbered steps and use the red boxes, arrows and labels in each illustration to locate controls.'),
      ('Scope','This guide covers the student interface available in November 2026. Use the official student access link. After updates, follow the current page prompts if minor layout differences occur.'),
      ('How to use this guide','Figures 01–23 cover corresponding operations in each language; a procedure may use two figures. Counts, times and accounts in screenshots are illustrative.'),
      ('Thesis privacy','Other users’ thesis text is not shown. Use your own report and review its findings against the original thesis.'),
      ('Using the results','The system provides assisted checks and suggestions. It does not replace review by a supervisor, school or university. Check each finding against the thesis and university requirements. No findings is not a certificate of compliance.')]
    for heading,text in zh if lang=='zh' else en:
        emit(r'\subsection*{'+esc(heading)+'}'+esc(text)+r'\par')

def overview(lang):
    emit(r'\clearpage\section{'+('系统概述' if lang=='zh' else 'System overview')+r'}\label{'+lang+':overview}')
    if lang=='zh':
        emit('系统围绕学位论文的规范性检查，帮助发现格式、文字、双语内容及部分论点论据问题，并把结果与 PDF 页面关联。可在检测过程中查看已有结果，完成后再按文件保存、复核和下载报告。')
        emit(r'\subsection*{开始前准备}')
        items=['本人可用的校园 jAccount 账号。','需要检测的学位论文：文字版 PDF，文件不超过 50 MB。不能上传非论文 PDF，也不能使用扫描版或纯图片 PDF。','保留 Word 或 LaTeX 源文件，便于根据复核结果自行修改。']
        workflow=['登录系统','上传论文','选择规则','开始检测','复核报告','修改源文件','上传新版本']
        end='建议首次按第 3 章完整完成一次流程。已有报告可直接到第 4 章；通知、邮件、设置和使用反馈见第 5 章。'
    else:
        emit('The system assists with thesis compliance checks, including formatting, wording, bilingual content and selected claim–evidence checks. Findings link to PDF pages. You can read available findings during a review, then revisit and download the saved report after completion.')
        emit(r'\subsection*{Before you begin}')
        items=['Your own working SJTU jAccount.','The degree thesis to review: a text-based PDF, no larger than 50 MB. Do not upload an unrelated PDF, a scan or an image-only PDF.','The Word or LaTeX source file, so you can make and verify revisions yourself.']
        workflow=['Sign in','Upload thesis','Choose checks','Start review','Verify findings','Edit source','Upload revision']
        end='For a first review, follow Chapter 3 in order. For an existing report, go to Chapter 4. Chapter 5 covers notifications, emails, preferences and feedback.'
    emit(r'\begin{itemize}'+''.join(r'\item '+esc(x) for x in items)+r'\end{itemize}')
    emit(r'\subsection*{'+('推荐流程' if lang=='zh' else 'Recommended workflow')+'}')
    emit(r'\begin{enumerate}'+''.join(r'\item '+esc(x) for x in workflow)+r'\end{enumerate}')
    emit(r'\note{'+esc(end)+'}')

def steps(m,lang):
    return r'\begin{enumerate}'+''.join(r'\item '+esc(x) for x in m[lang+'_steps'])+r'\end{enumerate}'
def figure(n,lang,caption,width=r'\linewidth',height='110mm'):
    number=f'{n:02}'
    label=('图 ' if lang=='zh' else 'Figure ')+number+'  '+caption
    return r'\pic{'+lang+'-'+number+'}{'+esc(caption)+'}{'+width+'}{'+height+'}{'+esc(label)+'}'
def module(m,lang,first=False):
    if not first:emit(r'\clearpage')
    emit(r'\subsection{'+esc(m[lang+'_title'])+r'}\label{'+lang+':'+m['id']+'}')
    emit(esc(m[lang+'_lead'])+r'\par')
    cap=m[lang+'_caption'];fs=m['figs']
    if m['id']=='export':
        emit(figure(12,lang,('下载入口' if lang=='zh' else 'Download control'),height='43mm'))
        emit(r'\noindent\begin{minipage}[t]{.43\linewidth}\vspace{0pt}\raggedright'+figure(13,lang,('选择格式' if lang=='zh' else 'Choose a format'),height='81mm')+r'\end{minipage}\hfill\begin{minipage}[t]{.53\linewidth}\vspace{0pt}\raggedright'+steps(m,lang)+r'\end{minipage}')
    elif m['id']=='settings' and lang=='en':
        emit(figure(19,lang,'Open the user menu',height='23mm'))
        emit(figure(20,lang,'Language and appearance',height='80mm'))
        emit(steps(m,lang))
    elif m['id']=='settings':
        emit(figure(19,lang,('打开用户菜单' if lang=='zh' else 'Open the user menu'),height='29mm'))
        emit(r'\noindent\begin{minipage}[t]{.46\linewidth}\vspace{0pt}\raggedright'+figure(20,lang,('语言与外观' if lang=='zh' else 'Language and appearance'),height='91mm')+r'\end{minipage}\hfill\begin{minipage}[t]{.50\linewidth}\vspace{0pt}\raggedright'+steps(m,lang)+r'\end{minipage}')
    elif m['id']=='systemfeedback' and lang=='en':
        emit(figure(21,lang,'Feedback entry',height='23mm'))
        emit(figure(22,lang,'Complete and submit',height='93mm'))
        emit(steps(m,lang))
    elif m['id']=='systemfeedback':
        emit(figure(21,lang,('使用反馈入口' if lang=='zh' else 'Feedback entry'),height='32mm'))
        emit(r'\noindent\begin{minipage}[t]{.46\linewidth}\vspace{0pt}\raggedright'+figure(22,lang,('填写与提交' if lang=='zh' else 'Complete and submit'),height='106mm')+r'\end{minipage}\hfill\begin{minipage}[t]{.50\linewidth}\vspace{0pt}\raggedright'+steps(m,lang)+r'\end{minipage}')
    elif m['id'] in ['repair'] or (m['id']=='findingfeedback' and lang=='zh'):
        emit(r'\noindent\begin{minipage}[t]{.46\linewidth}\vspace{0pt}\raggedright'+figure(fs[0],lang,cap,height='125mm')+r'\end{minipage}\hfill\begin{minipage}[t]{.50\linewidth}\vspace{0pt}\raggedright'+steps(m,lang)+r'\end{minipage}')
    else:
        height={'checks':'124mm','locate':'101mm','reading':'98mm','email':'123mm','summary':'90mm','delete':'87mm'}.get(m['id'],'109mm')
        emit(figure(fs[0],lang,cap,height=height))
        emit(steps(m,lang))
    emit(r'\note{'+esc(m[lang+'_note'])+'}')

def badgepage(lang):
    emit(r'\clearpage\subsection{'+('读懂徽标的颜色与图标' if lang=='zh' else 'Understand badge colours and icons')+r'}\label{'+lang+':badges}')
    emit(esc('不要只看颜色：同时看图标、文字、数字及所选筛选范围。浅色／深色模式底色会变化，下列以浅色模式示意。' if lang=='zh' else 'Use the icon, label, number and current filter together, rather than colour alone. Background shades vary with the light/dark theme; these examples use light-theme colours.')+r'\par')
    rows=[
      ('rose',r'\circlex','严重','Critical','红色圆圈叉号：需要优先复核的问题。数字表示当前显示范围内的严重结果数。','Red circle with a cross: a finding to prioritise. The number counts critical findings in the current scope.'),
      ('amber',r'\triangleicon','警告','Warnings','橙黄色三角感叹号：需要核对的规范问题。数字是警告数，不是失败规则数。','Amber warning triangle: an issue to check. The number counts warnings, not failed checks.'),
      ('blue',r'\infoicon','提示','Info','蓝色圆圈 i：信息性结果或需人工关注的提示，不等于严重错误。','Blue information icon: an informational finding or item for attention, not a critical error.'),
      ('violet',r'\shieldicon','未实现警告','Unverified','紫色盾牌感叹号：规则未实现警告，相关核验未能完整落实；不能当作已证实的论文错误。','Purple shield with an exclamation mark: verification could not be fully carried out. It is not a confirmed thesis error.'),
      ('progressink',r'\spinicon','正在检测','In progress','蓝灰色旋转圆环：规则仍在执行。“全部检查项”后的数字是仍在执行的规则数。','Blue-grey spinner: checks are still running. In the All checks summary, its number counts running checks.'),
      ('rose',r'\alerticon','检测失败','Failed','红色圆圈感叹号：检查执行失败，与红色叉号的严重问题不同。','Red circle with an exclamation mark: execution failed. This differs from a critical finding with a cross.'),
      ('slate',r'\questionicon','不适用','Not applicable','灰色圆圈问号：当前论文不适用该项检查。结合状态说明理解，不能据此推断所有内容合格。','Grey circle with a question mark: the check is not applicable. Read its explanation; this does not establish overall compliance.'),
      ('green',r'\checkicon','0','0','绿色圆圈对勾和 0：当前显示范围未发现对应问题，不能代替整份报告的结论。','Green circle with a check and zero: no matching finding in the displayed scope, not an overall certificate.'),
      ('violet',r'\flaskicon','实验性','Beta','紫色烧瓶：试验阶段的功能标签。它不是规则未实现警告，也不表示发现问题。','Purple flask: a beta-feature label. It is not an Unverified warning or a finding count.')]
    table_columns=r'@{}>{\raggedright\arraybackslash}m{39mm}@{\hspace{7mm}}>{\raggedright\arraybackslash}X@{}'
    table_start=(r'\begingroup\renewcommand{\tabularxcolumn}[1]{m{#1}}'
                 r'\renewcommand{\arraystretch}{1.1}\begin{tabularx}{\linewidth}{'+table_columns+r'}\toprule')
    row_spacing='10pt' if lang=='en' else '7pt'
    emit(r'\vspace{3mm}'+table_start)
    emit(('徽标示意 & 含义与使用方法' if lang=='zh' else 'Badge & Meaning and use')+r'\\\midrule\addlinespace[6pt]')
    for row_index,(color,icon,zh,en,zht,ent) in enumerate(rows):
        if row_index==4:
            emit(r'\bottomrule\end{tabularx}\endgroup\clearpage\subsection*{'+('执行状态与功能标签' if lang=='zh' else 'Execution status and feature labels')+'}')
            emit(table_start)
            emit(('徽标示意 & 含义与使用方法' if lang=='zh' else 'Badge & Meaning and use')+r'\\\midrule\addlinespace[6pt]')
        label=zh if lang=='zh' else en
        if color=='violet' and icon==r'\shieldicon' and lang=='zh':label='盾牌'
        background='progressbg' if color=='progressink' else color+'!8'
        label_text=(r'\textcolor{progressink}{'+esc(label)+'}') if color=='progressink' else esc(label)
        emit(r'\badge{'+color+'}{'+icon+'}{'+label_text+'}{'+background+'} & '+esc(zht if lang=='zh' else ent)+r'\\\addlinespace['+row_spacing+']')
    emit(r'\bottomrule\end{tabularx}\endgroup')
    emit(r'\note{'+esc('完整分类名称为“规则未实现警告”。汇总栏可能只显示紫色盾牌和数字，悬停可看说明。“未完成／无法判定”等需读具体状态；顶部蓝色盾牌“试点验证版”表示系统处于试点阶段；铃铛红点仅表示未读，二者都不是论文问题等级。' if lang=='zh' else 'The compact Unverified summary may show only a purple shield and number; hover for details. Read the explanations for incomplete or inconclusive checks. The blue Pilot shield in the header marks the system’s pilot phase. The bell’s red dot means unread notifications. Neither is a thesis finding category.')+'}')

def faq(lang):
    emit(r'\clearpage\section{'+('常见问题' if lang=='zh' else 'Frequently asked questions')+r'}\label{'+lang+':faq}')
    questions=[
      ('文件已是 PDF，为什么仍不能用？','文件还必须是学位论文的文字版 PDF，不是非论文文件、扫描件或纯图片，且不超过 50 MB。请从源文件重新导出，并先检查能否选择、复制正文。',
       'Why is my PDF unsuitable?','It must be a degree thesis in text-based PDF format, no larger than 50 MB. Unrelated PDFs, scans and image-only files are unsuitable. Export from the source and check that body text can be selected and copied.'),
      ('一直没有收到邮件，是否还没完成？','不一定。邮件可能延迟或进入垃圾邮件。直接登录网站，看铃铛通知和历史报告，不要只等邮件。',
       'No email has arrived. Is the review unfinished?','Not necessarily. Email may be delayed or filtered into spam. Sign in and check Notifications and Report history instead of relying only on email.'),
      ('没有发现问题，是否可以直接提交学校？','不能据此认定全部合格。还要看检查是否完成、是否存在规则未实现警告或无法判定状态，并按学校要求人工复核。',
       'Is a thesis with no findings ready to submit?','It does not establish full compliance. Check whether the selected checks completed and whether anything is Unverified or inconclusive, then review the thesis against university requirements.'),
      ('点击结果后没有精确高亮怎么办？','先确认已打开阅读工具，并选择合适的高亮方式。有些结果只有页码，没有精确定位框，可按页码核对上下文。',
       'Why is there no exact highlight after selecting a finding?','Open Reading tools and check the highlight mode. Some findings have only page-level locations; read the surrounding text on the indicated page.'),
      ('论文修改后用增量补跑吗？','不要。增量补跑仍使用旧报告保存的 PDF。论文内容修改后，需要导出新 PDF 并重新上传。',
       'Should I use Resume checks after revising the thesis?','No. Resume checks still uses the PDF saved with the old report. Export the revised thesis as a new PDF and upload it for a new review.'),
      ('停止检测、取消导出、删除报告一样吗？','不一样。停止检测中止任务；取消导出只停止文件准备；删除报告移除历史记录及保存的 PDF。成功取消不占额度，删除已生成报告不退额度。',
       'Are stopping, cancelling an export and deleting the same?','No. Stopping cancels a review task. Cancelling an export stops download preparation. Deleting removes a saved report and its stored PDF. A successful cancellation does not count toward the allowance; deleting a completed report does not restore a use.')]
    for question_index,(q,a,eq,ea) in enumerate(questions):
        if lang=='en' and question_index==3:emit(r'\clearpage\subsection*{More questions}')
        emit(r'\Needspace{32mm}\subsection*{'+esc(q if lang=='zh' else eq)+'}'+esc(a if lang=='zh' else ea)+r'\par')
    emit(r'\note{'+esc('其他异常可通过“使用反馈”提交，请附操作步骤和错误提示，不要提供密码或验证码。' if lang=='zh' else 'For other issues, use Feedback and include the steps and error message. Do not share passwords or verification codes.')+'}')

RULES=[
 ('正文公式引用目标缺失','检查正文所引用的公式是否有对应的可见公式编号。','Equation cross-references','Check that equations cited in the text have matching visible equation numbers.'),
 ('正文引文引用编号缺失','检查编号引文是否对应参考文献列表中的条目。','Citation matching','Match numbered citations to entries in the reference list.'),
 ('参考文献列表中存在未被正文引用的条目','找出参考文献列表中未在文档中引用的条目，再人工核查。','Uncited references','Identify reference-list entries with no citation in the document; review flagged entries manually.'),
 ('目录中的核心内容页码系统性错位','核对目录页码与对应正文标题所在页是否一致。','Contents page numbers','Compare contents page numbers with the pages containing the corresponding headings.'),
 ('引用格式错误','检查参考文献类型标识是否缺失或不完整，例如期刊的 [J]。','Reference type codes','Check for missing or invalid reference type codes, such as [J] for journal articles, where required.'),
 ('核心章节完整性','检查论文是否包含要求的核心章节。','Required thesis sections','Check that required thesis sections are present.'),
 ('中英文标点符号是否混用','检查中文语境误用英文标点、英文语境误用中文标点的情况。','Chinese/English punctuation','Find English punctuation used incorrectly in Chinese prose, or Chinese punctuation used incorrectly in English prose.'),
 ('关键词数量','检查中文关键词数量是否为 3—8 个。','Chinese keyword count','Check that the Chinese keyword list contains 3–8 keywords.'),
 ('摘要图表公式文献编号','检查中英文摘要中的图、表、公式及编号引文引用。','Abstract cross-references','Flag figure, table and equation numbers and numbered citations in Chinese and English abstracts.'),
 ('章标题另起一页','检查各章是否另起一页，标题上方是否残留上一章文字。','Chapter page breaks','Check that each chapter starts on a new page, without text from the previous chapter above its heading.'),
 ('引用的外部文献不存在','检索引用文献并评估是否存在；疑似不存在和检索未完成需分别处理。','Reference verification','Look up cited publications to assess whether they exist. Distinguish suspected nonexistent references from incomplete searches.'),
 ('正文错别字检测','检测正文中明确的中文错别字，不等于全面语法润色或英文拼写检查。','Chinese character errors','Find clear Chinese character errors in the main text. This is not a general grammar, style or English spelling check.'),
 ('中英文关键词语义对应','比较中英文关键词表达的概念是否相符、能否对应。','Bilingual keyword match','Check whether Chinese and English keyword lists express matching concepts and correspond to each other.'),
 ('中英文摘要内容一致性','比较中英文摘要的研究主题、方法、结果和结论是否存在实质差异。','Bilingual abstract agreement','Compare the abstracts for substantive differences in topic, methods, results and conclusions.'),
 ('论点论据一致性检测（实验性）','核对摘要中的数值性论断与对应研究章节的实验结果，不是全面判断学术质量。','Numerical claim verification (Beta)','Check numerical claims in the abstract against experimental results in the corresponding research chapters. This is not a general assessment of academic quality.')]
def rules(lang):
    emit(r'\clearpage\section*{'+('附录：检测规则速查' if lang=='zh' else 'Appendix: Check reference')+r'}\label{'+lang+':rules}')
    emit(r'\addcontentsline{toc}{section}{'+('附录：检测规则速查' if lang=='zh' else 'Appendix: Check reference')+'}')
    emit(esc('以下对应本版界面的 15 项规则，帮助理解检查范围；不是额外的论文格式标准。规则是否可选、实际执行结果及适用性，以当前页面为准。' if lang=='zh' else 'These are the 15 checks represented in this interface version. The descriptions explain scope; they are not additional thesis-formatting requirements. Follow the current interface for availability, execution results and applicability.'))
    for i,(zh,zht,en,ent) in enumerate(RULES,1):
        emit(r'\Needspace{26mm}\par\medskip{\sffamily\bfseries\color{navy}'+str(i)+'. '+esc(zh if lang=='zh' else en)+r'}\par '+esc(zht if lang=='zh' else ent)+r'\par')

if args.language!='both':
    metadata_title=('智慧学位 AI 评阅辅助系统 - 学生端操作手册' if args.language=='zh'
                    else 'Smart Degree · AI Review Assistant - Student User Guide')
    metadata_subject='学生端操作手册' if args.language=='zh' else 'Student User Guide'
    emit(r'\hypersetup{pdftitle={'+esc(metadata_title)+'},pdfsubject={'+esc(metadata_subject)+'},pdflang={'+('zh-CN' if args.language=='zh' else 'en')+'}}')

for lang in languages:
    emit(r'\clearpage')
    emit(r'\renewcommand{\currentlanguage}{'+lang+'}')
    emit(r'\renewcommand{\runningtitle}{'+('智慧学位 AI 评阅辅助系统 · 学生端操作手册' if lang=='zh' else 'Smart Degree · Student User Guide')+'}')
    titlepage(lang);contents(lang);intro(lang);overview(lang)
    for section in data['sections']:
        emit(r'\clearpage\section{'+esc(section[lang])+r'}\label{'+lang+':'+section['id']+'}')
        for i,m in enumerate(section['modules']):
            module(m,lang,first=i==0)
            if m['id']=='filter':badgepage(lang)
    faq(lang);rules(lang)
emit(r'\end{document}')
filename='student-guide.tex' if args.language=='both' else 'student-guide-'+args.language+'.tex'
(ROOT/filename).write_text('\n'.join(parts)+'\n',encoding='utf-8')
print('XeLaTeX source written:',filename,'; screenshot references:',sum(len(m['figs']) for s in data['sections'] for m in s['modules'])*len(languages))
