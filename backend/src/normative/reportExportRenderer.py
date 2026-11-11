"""Private single-language XeLaTeX report typesetting. Input is text data, never TeX source."""
import json,os,re,signal,subprocess,sys,zipfile,resource
from pathlib import Path
work=Path(sys.argv[1]).resolve();format=sys.argv[2];running=None
def stop(signum,frame):
    if running is not None:
        try:os.killpg(running.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    raise SystemExit(1)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
def limits():
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(50,50))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
def command(args,timeout):
    global running
    env={**os.environ,'openin_any':'p','openout_any':'p','TEXMFOUTPUT':str(work)}
    with (work/'process.log').open('ab') as log:
        running=subprocess.Popen(args,cwd=work,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,preexec_fn=limits)
        try:code=running.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(running.pid,signal.SIGKILL);running.wait();raise
        finally:running=None
        if code:raise RuntimeError('Typesetting process failed')
def esc(value):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_\allowbreak{}','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}','·':r'\brandseparator{}'}
    # Source punctuation must not become TeX smart-quote shorthand.
    mapping.update({"'":r'\textquotesingle{}','`':r'\textasciigrave{}','"':r'\textquotedbl{}','<':r'\textless{}','>':r'\textgreater{}'})
    # PDF extraction may carry nonprinting controls; never mutate the archived source.
    text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value or '')).replace('\r','')
    # Discretionary break points preserve even long technical identifiers verbatim.
    chunks=re.split(r'([A-Za-z0-9]{24,})',text)
    output=[]
    for chunk in chunks:
        if re.fullmatch(r'[A-Za-z0-9]{24,}',chunk):
            output.append(r'\allowbreak{}'.join(''.join(mapping.get(c,c) for c in chunk[i:i+16]) for i in range(0,len(chunk),16)))
        else:output.append(''.join(mapping.get(c,c)+(r'\allowbreak{}' if c in '/.-' else '') for c in chunk))
    result=''.join(output)
    return ''.join(r'\unicodechar{'+char+'}' if (0x370<=ord(char)<=0x52f or 0x2000<=ord(char)<0x2e80 or 0x1d400<=ord(char)<=0x1d7ff) else char for char in result)
head=r'''\documentclass[12pt,a4paper]{article}
\usepackage[left=25mm,right=25mm,top=23mm,bottom=23mm,footskip=12mm]{geometry}
\usepackage{fontspec,xeCJK,xcolor,needspace,framed,fancyhdr,hyperref,bookmark}
\setmainfont{Latin Modern Roman}\setCJKmainfont{Noto Serif CJK SC}
\newfontfamily\unicodefont{DejaVu Serif}\newfontfamily\cjkfallback{Noto Serif CJK SC}\newfontfamily\mathsymbols{Latin Modern Math}
\newcommand{\unicodechar}[1]{\iffontchar\font`#1 #1\else{\unicodefont\iffontchar\font`#1 #1\else{\cjkfallback\iffontchar\font`#1 #1\else{\mathsymbols #1}\fi}\fi}\fi}
\tracinglostchars=3
% Preserve source Unicode when a font shares glyphs between character aliases.
\XeTeXgenerateactualtext=1
\xeCJKDeclareCharClass{Default}{"00B7}
\newcommand{\brandseparator}{\unskip\nobreak\hspace{.25em}{\fontspec{Latin Modern Roman}\symbol{"00B7}}\nobreak\hspace{.25em}\ignorespaces}
\definecolor{ink}{HTML}{202A35}\definecolor{accent}{HTML}{96354A}\definecolor{muted}{HTML}{455363}\definecolor{edge}{HTML}{BBC4CF}\definecolor{mark}{HTML}{F6E6BE}
\color{ink}\setlength{\parindent}{2em}\setlength{\parskip}{6pt}
\newcommand{\bodyfont}{\normalfont\fontsize{12}{20}\selectfont}
\newcommand{\chapterhead}[2]{\par\Needspace{6\baselineskip}\addvspace{16pt}\noindent{\bfseries\fontsize{14}{20}\selectfont\textcolor{accent}{#1}\hspace{.7em}#2}\par\nobreak\vspace{4pt}}
\newcommand{\findinghead}[3]{\par\Needspace{6\baselineskip}\addvspace{12pt}\noindent{\bfseries #1\hspace{.6em}#2}\hspace{.8em}{\normalfont\textcolor{muted}{(#3)}}\par\nobreak\vspace{3pt}}
\newenvironment{citations}{\par\begingroup\def\FrameCommand{\textcolor{edge}{\vrule width .7pt}\hspace{10pt}}\MakeFramed{\advance\hsize-\width\FrameRestore\bodyfont\parindent=0pt\parskip=4pt}\bodyfont}{\par\endMakeFramed\endgroup}
\newcommand{\marked}[1]{\begingroup\setlength{\fboxsep}{0pt}\colorbox{mark}{\textcolor{accent}{#1}}\endgroup}
\hypersetup{colorlinks=true,urlcolor=ink,linkcolor=ink,pdfauthor={智慧学位 AI 评阅辅助系统},pdftitle={论文规范性检测报告 | Thesis compliance report},pdfdisplaydoctitle=true,bookmarksopen=true}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0pt}\fancyfoot[C]{\bodyfont\thepage}
\setlength{\emergencystretch}{3em}\hyphenpenalty=10000\exhyphenpenalty=10000\clubpenalty=10000\widowpenalty=10000
\begin{document}\bodyfont
'''
model=json.loads((work/'model.json').read_text(encoding='utf-8'))
metadata_en=model['reports'][0]['language']=='en'
head=head.replace('论文规范性检测报告 | Thesis compliance report','Thesis compliance report' if metadata_en else '论文规范性检测报告').replace('pdfauthor={智慧学位 AI 评阅辅助系统}','pdfauthor={Smart Degree · AI Review Assistant}' if metadata_en else 'pdfauthor={智慧学位 AI 评阅辅助系统}')
parts=[head]
def paragraph(text):
    if text:parts.append(esc(text)+r'\par')
def quote(text,label=''):
    parts.append(r'\begin{citations}\noindent '+(r'\textcolor{muted}{'+esc(label)+r'}\quad ' if label else '')+esc(text)+r'\par\end{citations}')
for index,report in enumerate(model['reports']):
    en=report['language']=='en';L=lambda zh,english:english if en else zh;s=report['summary']
    if index:parts.append(r'\clearpage')
    parts.append(r'\pdfbookmark[0]{'+L('中文报告','English report')+'}{'+('en' if en else 'zh')+'}')
    parts.append(r'{\centering\bfseries\fontsize{22}{30}\selectfont '+L('论文规范性检测报告','Thesis compliance report')+r'\par}\vspace{8pt}')
    parts.append(r'\noindent '+L('检测文件：','Document: ')+esc(report['document']['filename'])+r'\par')
    title=report['document'].get('title') or ''
    if title.strip() and title.strip()!='上传论文':parts.append(r'{\parskip=3pt\noindent '+L('论文题目：','Thesis title: ')+esc(title)+r'\par}')
    from datetime import datetime,timedelta,timezone
    try:date=datetime.fromisoformat(report['created_at'].replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8)));when=date.strftime('%d %b %Y, %H:%M' if en else '%Y-%m-%d %H:%M')
    except (ValueError,TypeError):when=report['created_at']
    stats=[]
    for key,zh,english in [('page_count',' 页',' pages'),('word_count',' 字',' characters')]:
        if report['document'].get(key) is not None:stats.append(f"{report['document'][key]:,}"+L(zh,english))
    parts.append(r'{\parskip=3pt\noindent '+esc(L('完成时间：','Completed: ')+when+' (UTC+08:00)'+(' · '+', '.join(stats) if stats else ''))+r'\par}')
    parts.append(r'\chapterhead{1}{'+L('检测综述','Review summary')+'}')
    paragraph(report['conclusion'])
    paragraph(L(f"本次记录 {s.get('finding_count',0)} 项检测结果：严重 {s.get('error_finding_count',0)}、警告 {s.get('warning_finding_count',0)}、规则未实现警告 {s.get('execution_warning_count',0)}、提示 {s.get('info_finding_count',0)}。",f"This review records {s.get('finding_count',0)} results: Critical: {s.get('error_finding_count',0)}; Warnings: {s.get('warning_finding_count',0)}; Unverified: {s.get('execution_warning_count',0)}; Info: {s.get('info_finding_count',0)}."))
    paragraph(L('请结合原文复核下列问题与建议。以下页码均为 PDF 文件页码；检测范围及执行情况见第三节。','Review the findings against the thesis text. Page references use physical PDF page numbers. Section 3 lists the review scope and execution status.'))
    parts.append(r'\chapterhead{2}{'+L('检测发现与修改建议','Findings and suggested actions')+'}')
    if not report['findings']:paragraph(L('未发现问题条目；请同时核对检测结论及未完成的规则。','No findings were reported. Also review the conclusion and any incomplete checks.'))
    for number,finding in enumerate(report['findings'],1):
        severity={'严重错误':'严重','error':L('严重','Critical'),'warning':L('警告','Warnings'),'info':L('提示','Info')}.get(finding['severity'],finding['severity'])
        parts.append(r'\findinghead{2.'+str(finding['number'])+'}{'+esc(finding['rule_title'])+'}{'+esc(severity)+'}')
        paragraph(finding['message'])
        for location in finding['locations']:
            label=location['label']+L(' · PDF 第 '+str(location['page'])+' 页',' · PDF p. '+str(location['page']))
            text=location['text'];cursor=0;marked=[]
            # JS offsets are UTF-16 units. Convert safely before placing display-only marks.
            def position(units):return len(text.encode('utf-16-le')[:units*2].decode('utf-16-le',errors='ignore'))
            for item in location.get('marks',[]):
                start,end=position(item['start']),position(item['end']);marked.extend([esc(text[cursor:start]),r'\allowbreak{}'.join((r'\space{}' if char.isspace() else r'\marked{'+esc(char)+'}') for char in text[start:end])]);cursor=end
            marked.append(esc(text[cursor:]));parts.append(r'\begin{citations}\noindent\textcolor{muted}{'+esc(label)+r'}\quad '+''.join(marked)+r'\par\end{citations}')
        if not finding['locations']:paragraph(L('未提供具体页码。','No specific page was provided.'))
        for number,value in enumerate(finding['suggestions']):
            if number in finding.get('source_suggestion_indices',[]):quote(value,L('修改建议（原文）','Suggested replacement (source text)'))
            else:paragraph(L('修改建议：','Suggested action: ')+value)
        for number,value in enumerate(finding['basis']):
            if number in finding.get('source_basis_indices',[]):quote(value,L('依据原文','Source basis'))
            else:paragraph(L('检查依据：','Basis: ')+value)
        for value in finding['evidence']:quote(value,L('参考证据','Source evidence'))
    parts.append(r'\chapterhead{3}{'+L('检测范围与执行情况','Review scope and execution')+'}')
    paragraph(L('执行状态不等同于问题等级。未能检测或无法判定的项目不能视为通过。','Execution status is separate from finding categories. Incomplete or inconclusive checks must not be treated as passed.'))
    paragraph(L('规则版本：','Rule version: ')+report['ruleset'])
    scopes={item['id']:item for item in report['scope']};runs={item['id']:item for item in report['rules']}
    ids=list(dict.fromkeys([item['id'] for item in report['scope']]+[item['id'] for item in report['rules']]))
    for number,rid in enumerate(ids,1):
        scope=scopes.get(rid,{});run=runs.get(rid,{})
        parts.append(r'\findinghead{3.'+str(number)+'}{'+esc(scope.get('title') or run.get('title') or rid)+'}{'+esc(run.get('status') or L('未记录执行状态','Execution status unavailable'))+'}')
        paragraph(scope.get('description',''))
        paragraph(run.get('message',''))
        for detail in run.get('details',[]):
            if detail['kind']=='quote':quote(detail['text'])
            elif detail['kind'] in ['title','heading','subheading','label']:parts.append(r'\noindent\textbf{'+esc(detail['text'])+r'}\par\nobreak')
            else:paragraph(detail['text'])
    if not ids:paragraph(L('未记录检测规则，无法确认本次检测范围。','No checks were recorded, so the review scope cannot be confirmed.'))
    paragraph(report['notice'])
    signature=[L('智慧学位 AI 评阅辅助系统','Smart Degree · AI Review Assistant'),L('上海交通大学研究生学位信息系统','Shanghai Jiao Tong University Graduate Degree Information System')]
    website='https://thesis-review.sjtu.edu.cn'
    parts.append(r'\par\Needspace{4\baselineskip}\vspace{26pt}{\parskip=2pt\noindent '+esc(signature[0])+r'\par}\nopagebreak')
    parts.append(r'{\parskip=2pt\noindent '+esc(signature[1])+r'\par}\nopagebreak')
    parts.append(r'\noindent '+esc(website)+r'\par')
parts.append(r'\end{document}');(work/'report.tex').write_text('\n'.join(parts),encoding='utf-8')
engine=os.environ.get('REPORT_EXPORT_XELATEX','/usr/bin/xelatex')
for _ in range(2):command([engine,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error','report.tex'],45)
info=subprocess.check_output([os.environ.get('REPORT_EXPORT_PDFINFO','/usr/bin/pdfinfo'),'report.pdf'],cwd=work,text=True,timeout=10)
pages=int(re.search(r'^Pages:\s+(\d+)',info,re.M).group(1))
if pages>150:
    sys.stderr.write('EXPORT_TOO_MANY_PAGES');sys.exit(2)
if format=='image':
    command([os.environ.get('REPORT_EXPORT_PDFTOPPM','/usr/bin/pdftoppm'),'-r','110','-png','report.pdf','page'],45)
    with zipfile.ZipFile(work/'report-images.zip','w',zipfile.ZIP_STORED) as archive:
        for page in sorted(work.glob('page-*.png')):archive.write(page,page.name)
