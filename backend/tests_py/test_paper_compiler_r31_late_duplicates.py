import importlib.util,os
from paper_compiler import fixed_r31
from paper_compiler.programs import execute_pure
if os.environ.get("R31_ASSET_PATH"):
    spec=importlib.util.spec_from_file_location("paper_compiler.late_candidate",os.environ["R31_ASSET_PATH"])
    fixed_r31=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixed_r31)
def run(kind,text,venue=None,url=None,known_pages=False):
    fields={"title":{"state":"observed","value":"A useful study"}}
    if venue:fields["container" if kind=="book_chapter" else "conference"]={"state":"observed","value":venue,"source_range":[text.index(venue),text.index(venue)+len(venue)],"evidence_ids":["e"]}
    if known_pages:fields["pages"]={"state":"confirmed_absent"}
    if url:fields["url"]={"state":"observed","value":url,"evidence_ids":["url-source"]}
    a={"coverage":{"e":{"status":"complete"}},"results":{"bibliography_fields":{"e":fields},"r31_source_context":{"e":{"resource_kind":{"state":"observed","value":kind,"evidence_ids":["e"]}}}}}
    if known_pages:a["results"]["external_work"]={"e":{"exists":{"state":"observed","value":True,"evidence_ids":["work"]},"available_fields":{"state":"observed","value":["pages"],"evidence_ids":["pages"]}}}
    return execute_pure(fixed_r31.build_r31_package()["code"],{"ir":{"nodes":[{"id":"e","kind":"BibliographyEntry","text":text}]},"analysis":a})[0]["status"]
def test_conference_dot_duplicate_before_pages():
    start="A useful study[C]//Example Conference"
    assert run("conference",start+". 2024. 2024: 4-9.","Example Conference")=="VIOLATION"
    assert run("conference",start+". 2024: 4-9.","Example Conference")=="PASS"
def test_repeated_url_requires_whole_repeated_publication_block():
    url="https://example.org/paper.pdf"
    block="2018, Example City, Country, February 18-21, 2018. Example Society, 2018. "
    start="A useful study[C/OL]//Example Symposium, "
    assert run("conference",start+block+url+".\n"+block+url+".",url=url)=="VIOLATION"
    assert run("conference",start+block+url+". "+url+".",url=url)!="VIOLATION"
def test_long_serial_suffix_and_tuple_required_not_just_same_year_pages():
    venue="ceedings of the Example Association on Computing Systems"
    start="A useful study[J]. Pro-"+venue+", 2020, 4(3): 1-29."
    assert run("journal_article",start+"\n"+venue+", 2020, 4(3): 1-29.")=="VIOLATION"
    assert run("journal_article",start+" 2020.\n"+venue+", 2020, 4(3): 1-29.")=="VIOLATION"
    assert run("journal_article",start+"\nOther translated publication, 2020, 4(3): 1-29.")!="VIOLATION"

def test_conference_book_form_retains_known_pages_condition():
    venue="Proceedings of the International Colloquium on Computing"
    assert run("book_chapter","A useful study[C]//"+venue+". Publisher, 2020.",venue=venue,known_pages=True)=="VIOLATION"
