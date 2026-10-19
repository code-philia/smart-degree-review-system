"""Actual archive failure shapes through the fixed detector sandbox."""
from paper_compiler_r31_fixtures import bind_type
from paper_compiler.fixed_r31 import build_r31_package
from paper_compiler.programs import execute_pure

def row(text,kind,electronic=True,container=None,verified_year=None):
    fields={"title":{"state":"observed","value":"A useful study"},
            "url":{"state":"confirmed_absent"},"doi":{"state":"confirmed_absent"},
            "access_date":{"state":"confirmed_absent"}}
    if container:
        fields["container"]={"state":"observed","value":container,"source_range":[text.index(container),text.index(container)+len(container)],"evidence_ids":["e"]}
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},
        "analysis":{"coverage":{"e":{"status":"complete"}},"results":{
            "bibliography_fields":{"e":fields},"r31_source_context":{"e":{
                "resource_kind":{"state":"observed","value":kind,"evidence_ids":["e"]},
                "electronic_medium":{"state":"observed","value":electronic,"evidence_ids":["e"]}}}}}}
    if verified_year:bind_type(payload["analysis"],"e",text,kind,year=verified_year,year_start=text.index(verified_year))
    return execute_pure(build_r31_package()["code"],payload)[0]

def test_bare_arxiv_identifier_does_not_prove_preprint_kind_or_medium():
    result=row("AUTHOR A. A useful study[J]. arXiv:2206.10321, 2022.","preprint")
    assert result["status"]!="VIOLATION"

def test_explicit_preprint_still_detects_wrong_type_but_not_present_locator_or_date():
    result=row("AUTHOR A. A useful study[J]. arXiv preprint arXiv:1705.03686, 2017[2024-10-02].","preprint",verified_year="2017")
    assert result["status"]=="VIOLATION"
    assert "类型标识" in result["message"]
    assert "访问路径" not in result["message"]
    assert "access_date" not in result["message"]

def test_complete_preprint_with_bare_locator_and_visible_date_is_not_missing_fields():
    result=row("AUTHOR A. A useful study[PP/OL]. arXiv preprint arXiv:1705.03686, 2017[2024-10-02].","preprint",verified_year="2017")
    assert result["status"]!="VIOLATION"

def test_other_is_not_positive_evidence_against_periodical_J():
    result=row("AUTHOR A. A useful study[J]. login: The USENIX Magazine, 2016, 41(1):6-12.","other",False)
    assert result["status"]!="VIOLATION"

def test_software_subject_does_not_prove_webpage_is_a_program_resource():
    result=row("AUTHOR A. A useful study[EB/OL]. https://example.org/software [2020-01-29].","computer_program")
    assert result["status"]!="VIOLATION"

def test_conference_book_form_can_state_proceedings_without_of():
    container="Proceedings: European Conference on Computing"
    result=row("AUTHOR A. A useful study[C]//"+container+". Publisher, 2020.","book_chapter",False,container)
    assert result["status"]!="VIOLATION"


def test_conference_genre_alone_does_not_disprove_serial_publication_form():
    result=row("AUTHOR A. A useful study[J]. Advances in Computing Systems, 2020, 34: 1-9.","conference",False)
    assert result["status"]!="VIOLATION"

def test_journal_container_alone_does_not_exclude_conference_paper_form():
    result=row("AUTHOR A. A useful study[C]//Computer Graphics Forum: vol. 42: 1. 2023: 319-355.","journal_article",False)
    assert result["status"]!="VIOLATION"

def test_manual_topic_does_not_prove_book_publication_form():
    result=row("AUTHOR A. A useful study[A/OL]. DDI 0487F.c. 2023 [2025-10-07]. https://example.org/manual.","book")
    assert result["status"]!="VIOLATION"

def test_database_name_does_not_prove_cited_database_resource():
    result=row("AUTHOR A. A useful study[Z]. 2017.","database",False)
    assert result["status"]!="VIOLATION"
