import pymupdf
import pytest
from paper_compiler.frontend import build_paper

def make(tmp_path, rows):
    doc=pymupdf.open();p=doc.new_page(width=600,height=800)
    p.insert_text((60,100),'References',fontsize=16)
    for text,x,y in rows:p.insert_text((x,y),text,fontsize=10)
    path=tmp_path/'columns.pdf';doc.save(path);doc.close()
    return [n for n in build_paper(path)['nodes'] if n['kind']=='BibliographyEntry']

@pytest.mark.parametrize('split',[True,False])
def test_bracketed_value_at_content_column_is_continuation(tmp_path,split):
    rows=[('[1]',60,140),('Author. Work[EB/OL]. 2024',90,140)] if split else [('[1] Author. Work[EB/OL]. 2024',60,140)]
    # Helvetica marker plus following space is 13.90pt at 10pt.
    content=90 if split else 60+pymupdf.get_text_length('[1] ',fontsize=10)
    rows += [('[2026]. https://example.org/',content,157),('[2] Other. Work[J]. 2023.',60,190)]
    entries=make(tmp_path,rows)
    assert [n['attrs']['key'] for n in entries]==['1','2']
    assert '[2026]. https://example.org/' in entries[0]['text']
    assert len(entries[0]['provenance'])==(3 if split else 2)

def test_new_column_number_is_not_previous_continuation(tmp_path):
    entries=make(tmp_path,[('[1] Author. Work[J]. 2024.',60,140),('[2] Other. Work[J]. 2023.',330,160)])
    assert [n['attrs']['key'] for n in entries]==['1','2']

def test_right_aligned_longer_true_number_remains_entry(tmp_path):
    right=74
    rows=[]
    for label,y in [('[9]',140),('[10]',170),('[2026]',200)]:
        x=right-pymupdf.get_text_length(label,fontsize=10)
        rows += [(label,x,y),('Author. Work[J]. 2024.',90,y)]
    assert [n['attrs']['key'] for n in make(tmp_path,rows)]==['9','10','2026']
