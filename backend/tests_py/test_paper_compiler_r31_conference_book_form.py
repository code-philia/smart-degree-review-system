"""GB/T 7714-2025 8.6.1 permits C with conference proceedings in book form."""
import importlib.util
import os
from paper_compiler import fixed_r31
from paper_compiler_r31_fixtures import bind_type
from paper_compiler.programs import execute_pure
if os.environ.get("R31_ASSET_PATH"):
    spec=importlib.util.spec_from_file_location("paper_compiler.conference_book_candidate",os.environ["R31_ASSET_PATH"])
    fixed_r31=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixed_r31)

def row(container,verified=True):
    title="A useful study";text="AUTHOR A. "+title+"[C]//"+container+". Publisher, 2020: 4-9."
    start=text.index(container)
    f={"state":"observed","value":container,"source_range":[start,start+len(container)],"evidence_ids":["container-source"]} if verified else {"state":"unknown"}
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":text}]},
             "analysis":{"coverage":{"entry":{"status":"complete"}},"results":{
             "bibliography_fields":{"entry":{"title":{"state":"observed","value":title},"container":f}},
             "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":"book_chapter","evidence_ids":["kind-source"]}}}}}}
    bind_type(payload["analysis"],"entry",text,"book_chapter",year="2020",year_start=text.index("2020"))
    return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]

def test_conference_book_form_needs_positive_grounded_container_evidence():
    allowed=row("Lecture Notes in Computer Science: Proceedings of the International Colloquium on Computing")
    assert allowed["status"]=="PASS" and "container-source" in allowed["evidence_ids"]
    unresolved=row("Handbook of Program Analysis")
    assert unresolved["status"]=="UNKNOWN"
    assert "提供方的图书或书章类型不能排除会议文献或汇编文献形式" in unresolved["message"]
    assert row("Proceedings of the International Colloquium on Computing",verified=False)["status"]!="PASS"
