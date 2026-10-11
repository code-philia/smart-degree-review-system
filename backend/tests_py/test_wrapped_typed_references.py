"""Explicit citations survive prose wraps without inventing object identities."""
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def document(prose, captions=(), second_scope=False):
    lines=[PdfLine(1,text,(60,70+i*22,540,84+i*22),600,800,font_size=12)
           for i,text in enumerate(prose)]
    lines.extend(PdfLine(1,f'{kind}{number} 独立实验结果',
                         (180,300+i*70,420,311+i*70),600,800,
                         font_size=10.5,bold=True) for i,(kind,number) in enumerate(captions))
    return PdfDocument(Path('unseen-wrapped-reference.pdf'),(PdfPage(1,600,800,tuple(lines)),))


@pytest.mark.parametrize('kind,rule',[('图','15'),('表','16')])
@pytest.mark.parametrize('suffix',['和9.4则分别展示了实验结果。','以及9.4所示。','至9.4的对比结果。'])
def test_wrapped_inherited_citations_are_parsed_after_paragraph_reconstruction(kind,rule,suffix):
    doc=document([f'相应实验结果见{kind}9.2',suffix],[(kind,'9.2'),(kind,'9.4')])
    result=detect_rules(build_index(doc),[15,16])
    assert result[rule]['findings']==[]


def test_missing_wrapped_target_is_reported_once_at_original_second_line():
    doc=document(['对比结果见图9.2','以及9.4所示。'],[('图','9.2')])
    index=build_index(doc)
    assert [r.number for r in index.figure_refs]==['9.2','9.4']
    result=detect_rules(index,[11])['11']['findings']
    assert len(result)==1 and result[0]['token']=='9.4'
    bbox=result[0]['location']['bounding_rect']
    assert bbox['page_number']==1 and bbox['y1']==92 and bbox['y2']==106


def test_distinct_ink_references_are_retained_and_no_single_ink_is_parsed_twice():
    doc=document(['先见图9.2以及图9.4，','再见图9.4所示。'],[('图','9.2'),('图','9.4')])
    index=build_index(doc)
    assert [r.number for r in index.figure_refs]==['9.2','9.4','9.4']
    assert [r.line.bbox[1] for r in index.figure_refs]==[70,70,92]


def test_wrapped_type_change_does_not_invent_a_figure():
    doc=document(['图9.2','以及表9.4所示。'],[('图','9.2'),('表','9.4')])
    index=build_index(doc)
    assert [r.number for r in index.figure_refs]==['9.2']
    assert [r.number for r in index.table_refs]==['9.4']
    assert detect_rules(index,[11])['11']['findings']==[]


def test_new_paragraph_quantity_is_not_inherited():
    doc=document(['结果见图9.2。','以及9.4 kg的负载。'],[('图','9.2')])
    index=build_index(doc)
    assert [r.number for r in index.figure_refs]==['9.2']
    assert detect_rules(index,[11])['11']['findings']==[]


def test_next_page_number_is_not_implicitly_a_cross_page_citation():
    first=PdfLine(1,'结果见图9.2',(60,730,540,744),600,800,font_size=12)
    second=PdfLine(2,'和9.4的负载。',(60,70,540,84),600,800,font_size=12)
    doc=PdfDocument(Path('unseen-page-boundary.pdf'),(
        PdfPage(1,600,800,(first,)),PdfPage(2,600,800,(second,))))
    assert [r.number for r in build_index(doc).figure_refs]==['9.2']


@pytest.mark.parametrize('barrier',['图7.1 独立实物题名','图7.1 独立实物题名............... 17'])
@pytest.mark.parametrize('has_target',[False,True])
def test_removed_caption_or_directory_is_still_a_prose_boundary(barrier,has_target):
    lines=[PdfLine(1,'这一段正文详细讨论实验的性能和结果，最后参考图9.2',(60,70,540,84),600,800,font_size=12),
           PdfLine(1,barrier,(180,86,420,97),600,800,font_size=10.5,bold=True),
           PdfLine(1,'以及9.4所示的实验条件。',(60,102,540,116),600,800,font_size=12),
           PdfLine(1,'图9.2 独立结果',(180,300,420,311),600,800,font_size=10.5,bold=True)]
    if has_target:lines.append(PdfLine(1,'图9.4 未引用结果',(180,400,420,411),600,800,font_size=10.5,bold=True))
    doc=PdfDocument(Path('unseen-intervening-title.pdf'),(PdfPage(1,600,800,tuple(lines)),))
    index=build_index(doc)
    assert [r.number for r in index.figure_refs]==['9.2']
    result=detect_rules(index,[11,15])
    assert result['11']['findings']==[]
    if has_target:assert '9.4' in [f['token'] for f in result['15']['findings']]


@pytest.mark.parametrize('barrier',['图7.1 独立实物题名','图7.1 独立实物题名............... 17'])
def test_removed_object_cannot_spread_external_source_qualification(barrier):
    lines=[PdfLine(1,'上一段正文介绍既有方法与相应设置，最后讨论文献[5]中的',(60,70,540,84),600,800,font_size=12),
           PdfLine(1,barrier,(180,86,420,97),600,800,font_size=10.5,bold=True),
           PdfLine(1,'图9.4展示了本节的实验结果。',(60,102,540,116),600,800,font_size=12),
           PdfLine(1,'图9.4 独立结果',(180,400,420,411),600,800,font_size=10.5,bold=True)]
    doc=PdfDocument(Path('unseen-source-boundary.pdf'),(PdfPage(1,600,800,tuple(lines)),))
    assert '9.4' in [r.number for r in build_index(doc).figure_refs]


@pytest.mark.parametrize('prose',['The efficient field verification appears in Figure9.2',
                                  'The eﬃcient ﬁeld veriﬁcation appears in Figure9.2'])
def test_normalized_character_coordinates_are_retained_across_prose_wrap(prose):
    from pdf_rules.numbering import normalize_text
    def line(text,box):
        offset=0;regions=[];advance=(box[2]-box[0])/len(text)
        for i,ch in enumerate(text):
            end=offset+len(normalize_text(ch))
            regions.append((offset,end,(box[0]+i*advance,box[1],box[0]+(i+1)*advance,box[3])))
            offset=end
        return PdfLine(1,text,box,600,800,font_size=12,text_regions=tuple(regions))
    first=line(prose,(60,70,540,84));second=line('and9.4 shows the result.',(60,92,540,106))
    doc=PdfDocument(Path('unseen-normalized-ink.pdf'),(PdfPage(1,600,800,(first,second)),))
    refs=build_index(doc).figure_refs
    assert [r.number for r in refs]==['9.2','9.4']
    assert refs[0].line.bbox==pytest.approx((60+prose.index('9.2')*480/len(prose),70,540,84))
    assert refs[1].line.bbox[1:4:2]==(92,106)
    assert refs[1].line.bbox[0]>60 and refs[1].line.bbox[2]<540


def test_implicit_path_does_not_rejoin_already_reconstructed_paragraphs():
    lines=[PdfLine(1,'这一段正文详细讨论不同实验的配置条件如下',(60,70,540,84),600,800,font_size=12),
           PdfLine(1,'图所示字样属于另一段文字，与上面的实验条件没有连接',(60,106,540,120),600,800,font_size=12),
           PdfLine(1,'这里继续介绍第二段的独立内容。',(60,128,540,142),600,800,font_size=12),
           PdfLine(1,'图9.2 未引用的独立结果',(180,300,420,311),600,800,font_size=10.5,bold=True)]
    doc=PdfDocument(Path('unseen-implicit-paragraph-boundary.pdf'),(PdfPage(1,600,800,tuple(lines)),))
    assert [f['token'] for f in detect_rules(build_index(doc),[15])['15']['findings']]==['9.2']
