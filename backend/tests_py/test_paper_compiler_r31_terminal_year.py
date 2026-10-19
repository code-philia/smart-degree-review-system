"""Terminal publication duplication is independent of extracted title/year overlap."""
import importlib.util
import os
from paper_compiler import fixed_r31
from paper_compiler.programs import execute_pure

if os.environ.get("R31_ASSET_PATH"):
    spec=importlib.util.spec_from_file_location("paper_compiler.terminal_candidate",os.environ["R31_ASSET_PATH"])
    fixed_r31=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixed_r31)

def verdict(title,ending):
    text="AUTHOR A. "+title+"[C]//Proceedings of Example Workshop."+ending
    start=text.index(title);year=text.index("2015")
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
             "analysis":{"coverage":{"entry":{"status":"complete"}},
             "results":{"bibliography_fields":{"entry":{
                 "title":{"state":"observed","value":title,"source_range":[start,start+len(title)]},
                 "year":{"state":"observed","value":"2015","source_range":[year,year+4]}}},
                 "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":"conference","evidence_ids":["entry"]}}}}}}
    return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]

def test_terminal_duplicate_overrides_unrelated_title_year_gap():
    title="Workshop 2015 shared task"
    assert verdict(title," 2015.")["status"]=="UNKNOWN"
    result=verdict(title," 2015. 2015.")
    assert result["status"]=="VIOLATION"
    assert "末尾相邻重复" in result["message"]

def test_title_intrusion_and_different_terminal_years_are_not_this_violation():
    assert verdict("A vali- 2015,\ndation study"," 2015.")["status"]=="UNKNOWN"
    assert verdict("Workshop 2015 shared task"," 2014. 2015.")["status"]=="UNKNOWN"
    assert verdict("A title. 2015. 2015."," 2015.")["status"]=="UNKNOWN"

def generic_verdict(text,kind):
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
             "analysis":{"coverage":{"entry":{"status":"complete"}},
             "results":{"bibliography_fields":{"entry":{"title":{"state":"observed","value":"A useful study"}}},
                 "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":kind,"evidence_ids":["entry"]}}}}}}
    return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]

def test_standalone_journal_year_before_doi_not_doi_year():
    original="AUTHOR A. A useful study[J/OL]. Journal of Examples, 2020, 3: 10-14. DOI: 10.1234/example.2020."
    assert generic_verdict(original,"journal_article")["status"]=="PASS"
    mutant=original.replace(". DOI:",". 2020. DOI:")
    assert generic_verdict(mutant,"journal_article")["status"]=="VIOLATION"

def test_exact_repeated_type_and_publication_segment_not_shared_venue_alone():
    segment="[C]//Conference on Examples. 2020: 10-14."
    original="AUTHOR A. A useful study"+segment
    assert generic_verdict(original,"conference")["status"]=="PASS"
    assert generic_verdict(original+"\nAnother title "+segment,"conference")["status"]=="VIOLATION"
    distinct=original+"\nAnother title "+segment.replace("10-14","20-24")
    assert generic_verdict(distinct,"conference")["status"]!="VIOLATION"

def test_orphan_conflicting_type_suffix_not_followed_by_a_new_work():
    original="AUTHOR A. A useful study[C]//Conference on Examples. 2020: 10-14."
    assert generic_verdict(original+" [M].","conference")["status"]=="VIOLATION"
    assert generic_verdict(original+" [M]. A separate book. Publisher, 2020.","conference")["status"]!="VIOLATION"

def boundary_verdict(kind,marker,publication,venue_field):
    title="A useful study";venue="Example Proceedings" if kind=="conference" else "Journal of Examples"
    text="AUTHOR A. "+title+marker+venue+publication
    start=text.index(venue)
    fields={"title":{"state":"observed","value":title},
            "container":{"state":"confirmed_absent"},
            venue_field:{"state":"observed","value":venue,"source_range":[start,start+len(venue)],"evidence_ids":["entry"]}}
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
             "analysis":{"coverage":{"entry":{"status":"complete"}},"results":{
             "bibliography_fields":{"entry":fields},
             "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":kind,"evidence_ids":["entry"]}}}}}}
    return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]

def test_conference_boundary_fallback_requires_observed_source_span():
    assert boundary_verdict("conference","[C]//",". 2023, 2023: 10341-\n10350.","conference")["status"]=="VIOLATION"
    assert boundary_verdict("conference","[C]//",". 2023: 10341-\n10350.","conference")["status"]=="PASS"

def test_journal_repeated_year_sequence_requires_separate_volume_and_pages():
    assert boundary_verdict("journal_article","[J].",", 2010, 2010,\n2010, 64(4): 330-342.","container")["status"]=="VIOLATION"
    assert boundary_verdict("journal_article","[J].",", 2010, 2010(4): 330-342. DOI: 10.1234/x.2010.","container")["status"]=="PASS"

def test_missing_type_from_exact_title_container_boundary_not_model_absence():
    def inspect(marker="",complete=True,title_range=True,title="A useful [J] notation study"):
        container="Journal of Examples";text="AUTHOR A. "+title+marker+". "+container+", 2023, 17: 1084000."
        fields={"title":{"state":"observed","value":title},
                "container":{"state":"observed","value":container,"source_range":[text.index(container),text.index(container)+len(container)]},
                "type_code":{"state":"unknown","reason":"field not returned"}}
        if title_range:fields["title"]["source_range"]=[text.index(title),text.index(title)+len(title)]
        payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
                 "analysis":{"coverage":{"entry":{"status":"complete" if complete else "partial"}},"results":{
                    "bibliography_fields":{"entry":fields},
                    "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":"journal_article","evidence_ids":["entry"]}}}}}}
        return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]
    assert inspect()["status"]=="VIOLATION"
    assert inspect("[J]")["status"]=="PASS"
    assert inspect(complete=False)["status"]!="VIOLATION"
    assert inspect(title_range=False)["status"]!="VIOLATION"
