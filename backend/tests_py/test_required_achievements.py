"""School-required back matter: native headings rather than prose/ToC mentions."""
import copy
from pathlib import Path
import sys
import pytest

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from paper_compiler.local_checks import core_parts, detect_ir
from test_fast_local_checks import sample_ir

PART = '学术论文和科研成果目录'

def paper(heading=None, kind='Heading', page=7):
    ir = sample_ir()
    ir['nodes'] = [n for n in ir['nodes'] if n['id'] != 'achievements-heading']
    for n in ir['nodes']:
        n['children'] = [c for c in n['children'] if c != 'achievements-heading']
    if heading:
        node = copy.deepcopy(next(n for n in ir['nodes'] if n['id'] == 'bib-heading'))
        node.update(id='test-achievements', kind=kind, text=heading)
        node['provenance'][0].update(page_index=page, bbox=[60,240,500,264], node_text_end=len(heading))
        ir['nodes'].append(node)
        ir['nodes'][0]['children'].append(node['id'])
    return ir

def missing(ir):
    return [f for f in detect_ir(ir,[34])['34']['findings'] if f['token']==PART]

def test_missing_school_section_is_reported():
    found = missing(paper())
    assert len(found)==1
    assert found[0]['message']==f'缺少{PART}：未在论文正文中识别到该章节。'
    assert found[0]['suggestion']==f'请补齐或核对{PART}；依据学校学位论文模板规范。'

@pytest.mark.parametrize('heading',[
    PART, '学 术 论 文 和 科 研 成 果 目 录', '学术论文与科研成果目录',
    '攻读学位期间发表的学术论文目录', '攻读硕士学位期间发表的学术论文',
    '攻读博士学位期间的研究成果', '攻读学位期间学术论文和科研成果目录',
    '发表论文和参加科研情况说明', '作者在学期间取得的科研成果',
    'Publications and Research Achievements', 'List of Publications',
    '论文和科研成果目录', 'Achievements', 'List of Research Achievements',
    '攻读博士期间已发表或录用的论文', '作者简介及攻读学位期间研究成果',
])
def test_school_heading_aliases_are_accepted(heading):
    assert core_parts(paper(heading)).get(PART) is True
    assert missing(paper(heading))==[]

@pytest.mark.parametrize('text,kind',[
    (PART+' ........... 81','ToCEntry'),(PART,'ToCEntry'),
    ('本文将介绍学术论文和科研成果目录。','Paragraph'),
    ('请参见学术论文和科研成果目录','Paragraph'),
    ('[1] 张三. 学术论文和科研成果目录[J]. 期刊, 2020.','BibliographyEntry'),
    ('研究成果总结','Heading'),('个人简历','Heading'),('参考文献','Heading'),
])
def test_mentions_and_other_back_matter_do_not_supply_the_section(text,kind):
    assert len(missing(paper(text,kind)))==1

def test_toc_ancestor_does_not_supply_the_section():
    ir=paper(PART)
    ir['nodes'].append(dict(id='toc-parent',kind='ToC',text=None,attrs={},children=['test-achievements'],provenance=[]))
    assert len(missing(ir))==1

def test_running_header_does_not_supply_the_section():
    ir=paper(PART,'UnknownBlock')
    ir['nodes'][-1]['attrs']={'role':'running_header'}
    assert len(missing(ir))==1

def test_scanned_back_pages_do_not_prove_absence():
    ir=paper()
    ir['coverage']['pages'].update(status='partial',core_sections_status='complete')
    assert missing(ir)==[]
    assert PART not in detect_ir(ir,[34])['34']['checked_parts']

def test_research_article_does_not_require_university_back_matter():
    ir=paper()
    ir['metadata']={'document_admission':{'structure':{'profile':'research-article'}}}
    assert missing(ir)==[]

def test_deleted_live_heading_is_not_restored_from_original_layout():
    ir=paper(PART)
    ir['layout']['pages'][7]['lines']=[dict(text=PART,bbox=[60,240,500,264],font_size=18)]
    ir['nodes'][-1]['text']='附录'
    assert len(missing(ir))==1

def native_pdf(tmp_path, title, *, split=False, contents_only=False):
    import pymupdf
    from paper_compiler.frontend import _build_source_tree
    path=tmp_path/'native-achievements.pdf'
    with pymupdf.open() as doc:
        if contents_only:
            page=doc.new_page(width=600,height=800)
            page.insert_text((60,100),'目录',fontsize=20,fontname='china-s')
            page.insert_text((60,145),PART+' ............ 81',fontsize=12,fontname='china-s')
        page=doc.new_page(width=600,height=800)
        page.insert_text((60,120),'参考文献',fontsize=20,fontname='china-s')
        page.insert_text((60,170),'[1] Smith. A genuine work[J]. Journal of Tests, 2020.',fontsize=12)
        if not contents_only:
            page=doc.new_page(width=600,height=800)
            if split:
                for i,char in enumerate(title):
                    page.insert_text((60+i*25,130),char,fontsize=18,fontname='china-s')
            else:page.insert_text((60,130),title,fontsize=18,fontname='helv' if title.isascii() else 'china-s')
            page.insert_text((60,210),'[1] Author. An accepted publication[J]. Journal, 2024.',fontsize=12)
        doc.save(path)
    return _build_source_tree(path,include_citations=False)

@pytest.mark.parametrize('title',[PART,'论文和科研成果目录','攻读学位期间发表的学术论文目录',
    'Publications and Research Achievements','List of Research Achievements','Achievements'])
def test_native_back_heading_after_references_passes(tmp_path,title):
    assert missing(native_pdf(tmp_path,title))==[]

def test_native_split_character_heading_passes(tmp_path):
    assert missing(native_pdf(tmp_path,PART,split=True))==[]

def test_native_contents_entry_alone_does_not_pass(tmp_path):
    assert len(missing(native_pdf(tmp_path,PART,contents_only=True)))==1
