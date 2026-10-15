from pdf_rules import caption_rules
from pdf_rules.mineru_layout import LayoutObject


def test_distant_pages_are_not_repeatedly_matched(monkeypatch):
    objects=[]
    for page in range(1,101):
        objects.extend([
            LayoutObject('figure',page,(100,100,300,250),'',600,800),
            LayoutObject('figure_caption',page,(100,260,300,280),f'Figure {page} Results',600,800),
            LayoutObject('table',page,(100,400,300,500),'',600,800),
            LayoutObject('table_caption',page,(100,370,300,390),f'Table {page} Results',600,800)])
    # The source may not arrive sorted by page or object kind.
    objects.reverse()
    original=caption_rules._matches;calls=[]
    def counted(target,caption):
        calls.append((target.page_number,caption.page_number))
        return original(target,caption)
    monkeypatch.setattr(caption_rules,'_matches',counted)
    result=caption_rules.detect_caption_rules(objects,[13,14])
    assert all(not value['findings'] for value in result.values())
    assert len(calls)<=400


def test_allowed_cross_page_titles_and_missing_title_remain():
    objects=[
        LayoutObject('figure',1,(100,650,300,790),'',600,800),
        LayoutObject('figure_caption',2,(100,30,300,50),'Figure 1 Results',600,800),
        LayoutObject('table_caption',3,(100,740,300,760),'Table 1 Results',600,800),
        LayoutObject('table',4,(100,50,300,180),'',600,800),
        LayoutObject('figure',6,(100,100,300,250),'',600,800)]
    result=caption_rules.detect_caption_rules(objects,[13,14])
    assert [f['page'] for f in result['13']['findings']]==[6]
    assert result['14']['findings']==[]
