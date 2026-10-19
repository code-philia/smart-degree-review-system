"""R31 checks the independently verified publication type, not a model's guessed work genre."""
from paper_compiler.fixed_r31 import build_r31_package
from paper_compiler.programs import execute_pure

def test_r31_has_no_model_resource_reclassification_request():
    package=build_r31_package()
    assert package["program_spec"]["analysis_requests"]==[]
    assert "r31_source_context" not in package["program_spec"]["requires"]

def test_guessed_preprint_cannot_invalidate_a_syntactically_valid_J_entry():
    text="AUTHOR A. A useful study[J]. arXiv preprint arXiv:1705.03686, 2017."
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},
        "analysis":{"coverage":{"e":{"status":"complete"}},"results":{
            "bibliography_fields":{"e":{"title":{"state":"observed","value":"A useful study"},"type_code":{"state":"observed","value":"J"},"access_date":{"state":"confirmed_absent"}}},
            "r31_source_context":{"e":{"resource_kind":{"state":"observed","value":"preprint","evidence_ids":["e"]},"electronic_medium":{"state":"observed","value":True,"evidence_ids":["e"]}}}}}}
    rows=execute_pure(build_r31_package()["code"],payload)
    assert rows[0]["status"]!="VIOLATION"


def test_verified_same_version_publication_type_conflict_remains_detectable():
    text="AUTHOR A. A useful study[M]. Journal of Examples, 2020. doi:10.1234/verified.1"
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},
        "analysis":{"coverage":{"e":{"status":"complete"}},"evidence":[{"id":"verified","provider":"crossref","status":"ok","work":{"title":"A useful study","year":2020,"type":"journal-article","doi":"10.1234/verified.1"}}],"results":{
            "bibliography_fields":{"e":{"title":{"state":"observed","value":"A useful study"},"year":{"state":"observed","value":"2020","source_range":[text.index("2020"),text.index("2020")+4]},"type_code":{"state":"observed","value":"M"}}},
            "external_work":{"e":{"exists":{"state":"observed","value":True,"evidence_ids":["verified"]}}}}}}
    rows=execute_pure(build_r31_package()["code"],payload)
    assert rows[0]["status"]=="VIOLATION"
    assert "verified" in rows[0]["evidence_ids"]

def test_wrong_year_external_version_cannot_trigger_type_alarm():
    text="AUTHOR A. A useful study[J]. arXiv:2206.10321, 2022."
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},
        "analysis":{"coverage":{"e":{"status":"complete"}},"evidence":[{"id":"later","provider":"crossref","status":"ok","work":{"title":"A useful study","year":2026,"type":"preprint"}}],"results":{
            "bibliography_fields":{"e":{"title":{"state":"observed","value":"A useful study"},"year":{"state":"observed","value":"2022","source_range":[text.index("2022"),text.index("2022")+4]},"type_code":{"state":"observed","value":"J"}}},
            "external_work":{"e":{"exists":{"state":"observed","value":True,"evidence_ids":["later"]}}}}}}
    rows=execute_pure(build_r31_package()["code"],payload)
    assert rows[0]["status"]!="VIOLATION"


def _typed_entry(text, typ, **metadata):
    year="2017"
    work={"title":"A useful study","year":2017,"type":typ,**metadata}
    fields={"title":{"state":"observed","value":"A useful study"},"year":{"state":"observed","value":year,"source_range":[text.index(year),text.index(year)+4]},"access_date":{"state":"confirmed_absent"},"pages":{"state":"observed","value":"1-9"}}
    if "NeurIPS" in text:
        fields["container"]={"state":"observed","value":"NeurIPS","source_range":[text.index("NeurIPS"),text.index("NeurIPS")+7],"evidence_ids":["e"]}
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},"analysis":{"coverage":{"e":{"status":"complete"}},"evidence":[{"id":"verified","status":"ok","work":work}],"results":{"bibliography_fields":{"e":fields},"external_work":{"e":{"exists":{"state":"observed","value":True,"evidence_ids":["verified"]}}}}}}
    return execute_pure(build_r31_package()["code"],payload)[0]

def test_same_year_preprint_alias_does_not_retype_published_conference():
    result=_typed_entry("AUTHOR A. A useful study[C]//NeurIPS, 2017, 30: 1-9.","preprint",doi="10.48550/arXiv.1706.03762",url="https://arxiv.org/abs/1706.03762")
    assert result["status"] != "VIOLATION"

def test_visible_doi_mismatch_cannot_fall_back_to_matching_container():
    result=_typed_entry("AUTHOR A. A useful study[J]. NeurIPS, 2017. doi:10.1234/published", "preprint",doi="10.48550/arXiv.1706.03762",container="NeurIPS")
    assert result["status"] != "VIOLATION"

def test_coarse_book_chapter_type_cannot_exclude_G_collection():
    result=_typed_entry("AUTHOR A. A useful study[G]//Collected works. 2017: 1-9. doi:10.1234/chapter", "book-chapter",doi="10.1234/chapter")
    assert result["status"] != "VIOLATION"

def test_coarse_book_type_cannot_exclude_C_conference_form():
    result=_typed_entry("AUTHOR A. A useful study[C]//A computing collection. 2017: 1-9. doi:10.1234/book", "book",doi="10.1234/book")
    assert result["status"] != "VIOLATION"


def test_pages_from_another_alias_cannot_trigger_missing_pages_alarm():
    text="AUTHOR A. A useful study[C]//Conference on Examples. 2017. doi:10.1234/conference"
    venue="Conference on Examples"
    fields={"title":{"state":"observed","value":"A useful study"},"year":{"state":"observed","value":"2017","source_range":[text.index("2017"),text.index("2017")+4]},"container":{"state":"observed","value":venue,"source_range":[text.index(venue),text.index(venue)+len(venue)],"evidence_ids":["e"]},"pages":{"state":"confirmed_absent"}}
    evidence=[{"id":"bound","status":"ok","work":{"type":"proceedings-article","year":2017,"doi":"10.1234/conference"}}, {"id":"alias","status":"ok","work":{"type":"journal-article","year":2017,"doi":"10.1234/journal","pages":"10-20"}}]
    external={"exists":{"state":"observed","value":True,"evidence_ids":["bound","alias"]},"available_fields":{"state":"observed","value":["pages"],"evidence_ids":["bound","alias"]}}
    payload={"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},"analysis":{"coverage":{"e":{"status":"complete"}},"evidence":evidence,"results":{"bibliography_fields":{"e":fields},"external_work":{"e":external}}}}
    assert execute_pure(build_r31_package()["code"],payload)[0]["status"]!="VIOLATION"
