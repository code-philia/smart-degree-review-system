"""Establish document identity from source text before creating any Paper nodes.

This is independent of individual completeness checks: a thesis missing an
abstract or bibliography can still be a thesis. Neither its filename nor PDF
metadata, page count or an isolated occurrence of '论文' establishes identity.
"""
import hashlib
import re
import statistics
import unicodedata
from pathlib import Path

import pymupdf
from .structure import assess_structure, section_display_name

VERSION = 'paper-admission/2.0'
_SPACE = re.compile(r'\s+')
_NUMBER = re.compile(r'^(?:第[一二三四五六七八九十百\d]+[章篇节]|chapter\s+\d+|[IVXLCDM]+[.]\s*|\d+(?:[.．]\d+)*[.．、]?)[\s:：-]*', re.I)
_RESEARCH = re.compile(r'^(?:绪论|绪言|引言|引论|相关工作|研究背景|研究方法|方法(?:研究)?|实验(?:评估|结果|分析)?|结果(?:与讨论)?|总结(?:与展望)?|结论(?:与展望)?|introduction|background|related\s+work|methods?|methodology|experiments?(?:\s+and\s+results)?|evaluation|results?(?:\s+and\s+discussion)?|discussion|conclusions?(?:\s+and\s+future\s+work)?)$', re.I)
_NON_PAPER = re.compile(
    r'(?:推荐|申请|登记|审批|评审|报名|鉴定|验收|备案|评议|信息采集|申报)表(?:[（(].{0,30}[）)])?$'
    r'|^(?:个人简历|求职简历|履历表|课程表|成绩单|发票|收据|合同|会议议程|会议通知|教学课件|课程讲义|教学大纲)(?:[:：\s].*)?$'
    r'|(?:增值税.*发票|(?:用户|使用|操作|参考|产品)手册|(?:论文|学位).*(?:撰写|写作|编写|格式).*(?:规范|指南|要求|规定|模板|细则))$'
    r'|^(?:curriculum\s+vitae|resume|syllabus|universal\s+declaration\s+of\s+human\s+rights)$'
    r'|^(?:invoice|receipt)(?:\s*(?:no\.?|#)?\s*\d[\w-]*)?$'
    r'|^(?:.{0,50}\b)?(?:application|recommendation)\s+form$'
    r'|^(?:lecture\s+(?:notes|slides))(?:\s*[:—-].*)?$'
    r'|^(?:.{0,50}\b)?(?:reference|user|instruction|installation)\s+manual(?:\s*[\dv. -]+)?$', re.I)
_COVER = re.compile(r'^(?:.{0,12})?(?:博士|硕士|学士)(?:研究生)?(?:学位|毕业)?论文(?:[（(].{0,15}[）)])?$|^(?:.{0,20}\s)?(?:doctoral\s+(?:thesis|dissertation)|master.?s\s+thesis|a\s+(?:thesis|dissertation))$', re.I)


class DocumentAdmissionError(ValueError):
    def __init__(self, assessment):
        self.assessment = assessment
        super().__init__('PDF 未通过论文身份校验，不能创建 Paper Model：' + assessment['reason'])


class DocumentStructureError(DocumentAdmissionError):
    def __init__(self, assessment):
        self.assessment = assessment
        ValueError.__init__(self, '论文结构语法错误，Paper Model 编译失败：' + assessment['reason'])


def assess_pages(pages):
    """Accept independent academic signals; return explicit uncertainty on failure."""
    rows = [(page.get('page_index', index), line['text'].strip())
            for index, page in enumerate(pages) for line in page.get('lines', []) if line['text'].strip()]
    normalized = [(index, unicodedata.normalize('NFKC', text)) for index, text in rows]
    compact = [(index, _SPACE.sub('', text).lower()) for index, text in normalized]
    # Inspect the document's opening identity, never appendices or quoted prose.
    first_page = normalized[0][0] if normalized else 0
    opening = [text for index, text in normalized if index == first_page][:16]
    non_paper = any(_NON_PAPER.search(_SPACE.sub('', text) if re.search(r'[\u4e00-\u9fff]', text) else text)
                    for text in opening if len(text) <= 130)
    cover = any(index < 8 and len(text) <= 80 and _COVER.fullmatch(text)
                for index, text in normalized) or any(index < 8 and _COVER.fullmatch(text) for index, text in compact)
    abstract = any(re.match(r'^(?:摘要|中文摘要|英文摘要|abstract)(?:[:：—–\s-]|$)', text, re.I) for _, text in normalized)
    references = any(text in {'参考文献', '參考文獻', 'references', 'bibliography'} for _, text in compact)
    keywords = any(re.match(r'^(?:关键词|关键字|key\s*words?|index\s+terms)(?:\s*[:：—–-]\s*|\s+)\S', text, re.I) for _, text in normalized)
    sections = set()
    research = set()
    for _, text in normalized:
        if len(text) > 90 or re.search(r'(?:\.\s*){3,}|…|·{3,}', text):
            continue
        heading = _NUMBER.sub('', text).strip()
        if heading != text and len(heading) >= 2:
            sections.add(_SPACE.sub('', heading).lower())
        if _RESEARCH.fullmatch(heading):
            research.add(heading.lower())
    joined = '\n'.join(text for _, text in normalized)
    units = len(re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9]+', joined))
    publisher = bool(re.search(r'\bdoi\s*:|arxiv\s*:|\bjournal\s+of\b|\bproceedings\s+of\b', joined, re.I))
    signals = {'academic_cover': cover, 'abstract': abstract, 'references': references,
               'keywords': keywords, 'section_count': len(sections),
               'research_heading_count': len(research), 'text_units': units}
    # No single mandatory chapter: required-section rules must still catch omissions.
    thesis = cover and units >= 200 and (len(sections) >= 2 or len(research) >= 2
                                         or (abstract and (references or keywords)))
    article = units >= 150 and ((abstract and (references or len(research) >= 2)
                                and (research or keywords))
                               or (references and len(research) >= 2 and (publisher or keywords)))
    accepted = bool(not non_paper and (thesis or article))
    reason_code = 'paper_structure_confirmed' if accepted else 'non_paper_identity' if non_paper else 'paper_identity_unconfirmed'
    reason = ('已识别论文正文及相互印证的学术结构。' if accepted else
              '文档首页表明这是表单、说明材料或其他非论文文档。' if non_paper else
              '未能确认论文正文及学术结构；文件可能为非论文、仅有封面或文字不可读取的扫描件。')
    return {'version': VERSION, 'status': 'accepted' if accepted else 'rejected',
            'reason_code': reason_code, 'reason': reason, 'signals': signals}


def assess_pdf(pdf):
    path = Path(pdf)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError('encrypted PDF')
            # Preserve source lines within columns, matching the Paper frontend.
            # Plain-text sort=True merges unrelated columns on the same baseline.
            pages = []
            for index, page in enumerate(doc):
                page.set_rotation(0)
                data = page.get_text('rawdict', sort=True,
                                     flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
                lines = [{'text': ''.join(char['c'] for span in line.get('spans', []) for char in span.get('chars', [])), 'bbox': list(line['bbox']),
                          'font_size': statistics.median([span['size'] for span in line.get('spans', []) for char in span.get('chars', [])] or [0]),
                          'is_bold': any(span.get('flags', 0) & 16 for span in line.get('spans', []))}
                         for block in data['blocks'] if block.get('type') == 0
                         for line in block.get('lines', [])]
                pages.append({'page_index': index, 'height': page.rect.height, 'lines': lines})
        assessment = assess_document_pages(pages)
    except Exception:
        assessment = {'version': VERSION, 'status': 'rejected', 'reason_code': 'pdf_unreadable',
                      'reason': 'PDF 文件损坏、加密或无法读取，不能确认论文身份。', 'signals': {}}
    return {**assessment, 'sha256': digest}


def assert_paper_pages(pages, *, allow_incomplete_structure=False):
    assessment = assess_document_pages(pages)
    if assessment['status'] != 'accepted':
        # Identity has already been established before the structure stage.
        # Partial compilation may relax chapter grammar, never that identity gate.
        if allow_incomplete_structure and assessment.get('stage') == 'structure':
            return {**assessment, 'status': 'accepted', 'stage': 'partial'}
        error = DocumentStructureError if assessment.get('stage') == 'structure' else DocumentAdmissionError
        raise error(assessment)
    return assessment


def assess_document_pages(pages):
    assessment = assess_pages(pages)
    if assessment['status'] != 'accepted':
        return {**assessment, 'stage': 'identity'}
    structure = assess_structure(pages, assessment)
    if structure['status'] != 'accepted':
        reasons = []
        for name in structure['missing_sections']:
            reasons.append('缺少' + section_display_name(name, structure['profile']) + '：未在论文正文中识别到该章节。')
        for name in structure['incomplete_sections']:
            reasons.append(section_display_name(name, structure['profile']) + '不完整：'
                           + '；'.join(structure['abstract_sections'][name]['issues']) + '。')
        return {**assessment, 'status': 'rejected', 'stage': 'structure',
                'reason_code': 'paper_structure_incomplete',
                'reason': ''.join(reasons),
                'structure': structure,
                **{key: value for key, value in structure.items() if key != 'status'}}
    return {**assessment, 'stage': 'complete', 'structure': structure}
