"""Direct sandbox tests for journal year position and unresolved field roles."""
import pytest
from paper_compiler.programs import execute_pure
from paper_compiler import fixed_r31

def observed(text, value, start=None):
    start = text.index(value) if start is None else start
    return {"state":"observed", "value":value, "source_range":[start,start+len(value)],"evidence_ids":["entry"]}

def check(text, title="A useful study", container="Journal of Studies", kind="journal_article", year_start=None):
    fields={"title":observed(text,title), "container":observed(text,container),
            "year":observed(text,"2020",year_start)}
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
             "analysis":{"coverage":{"entry":{"status":"complete"}},
                         "results":{"bibliography_fields":{"entry":fields},
                                    "r31_source_context":{"entry":{
                                      "resource_kind":{"state":"observed","value":kind,"evidence_ids":["entry"]},
                                      "electronic_medium":{"state":"unknown"}}}}}}
    return execute_pure(fixed_r31.build_r31_package()["code"], payload)[0]

@pytest.mark.parametrize("marker", ["J", "J/OL"])
def test_journal_front_duplicate_publication_year(marker):
    text=f"AUTHOR A. A useful study[{marker}]. 2020. Journal of Studies, 2020, 12: 4-6. DOI: 10.1234/example."
    row=check(text)
    assert row["status"] == "VIOLATION"
    assert "刊名之间" in row["message"]

@pytest.mark.parametrize("text", [
    "AUTHOR A. 2020. A useful study[J]. Journal of Studies, 2020, 12: 4-6.",
    "AUTHOR A. A useful study[J]. Journal of Studies, 2020, 12: 4-6. DOI: 10.1234/2020.123.",
    "AUTHOR A. A useful study[J]. Journal of Studies, 2020, 12: 4-6.",
])
def test_valid_journal_year_roles(text):
    assert check(text)["status"] == "PASS"

def test_conference_name_year_is_not_extra_publication_year():
    text="AUTHOR A. A useful study[C]//Proceedings of Conference 2020. 2020: 4-6."
    assert check(text,container="Proceedings of Conference 2020",kind="conference",year_start=text.rindex("2020"))["status"] == "PASS"

def test_title_publication_year_overlap_is_unknown_not_violation():
    title="A useful study of vio- 2020,\nlation"
    text=f"AUTHOR A. {title}[C]//Proceedings of Conference. 2020: 4-6."
    row=check(text,title=title,container="Proceedings of Conference",kind="conference")
    assert row["status"] == "UNKNOWN"
    assert "来源范围重叠" in row["message"]

def test_title_year_with_separate_publication_year_is_not_violation():
    title="Studies of 2020"
    text=f"AUTHOR A. {title}[J]. Journal of Studies, 2020, 12: 4-6."
    assert check(text,title=title,year_start=text.rindex("2020"))["status"] == "PASS"

def test_conference_adjacent_duplicate_publication_year():
    text="AUTHOR A. A useful study[C]//Proceedings of Conference. 2020, 2020: 4-6."
    row=check(text,container="Proceedings of Conference",kind="conference")
    assert row["status"] == "VIOLATION"
    assert "相邻重复" in row["message"]

def test_conference_year_pair_inside_container_is_not_publication_duplicate():
    text="AUTHOR A. A useful study[C]//Proceedings of Conference 2020, 2020: Workshop series. 2020: 4-6."
    assert check(text,container="Proceedings of Conference 2020, 2020: Workshop series",kind="conference",year_start=text.rindex("2020"))["status"] == "PASS"

@pytest.mark.parametrize("suffix", [" DOI: 10.1234/example.", " https://example.org/work."])
@pytest.mark.parametrize("publication,expected", [("2020, 2020", "VIOLATION"), ("2020", "PASS")])
def test_conference_publication_year_with_identifier_tail(suffix, publication, expected):
    text="AUTHOR A. A useful study[C]//Proceedings of Conference. " + publication + ": 4-6." + suffix
    assert check(text,container="Proceedings of Conference",kind="conference")["status"] == expected

def test_conference_book_form_exception_not_rejected_by_resource_kind():
    text="AUTHOR A. A useful study[M]//Proceedings of Conference. 2020: 4-6."
    row=check(text,container="Proceedings of Conference",kind="conference")
    assert row["status"] == "UNKNOWN"
    assert "图书形式" in row["message"]
