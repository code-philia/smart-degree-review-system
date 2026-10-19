"""Conditional pages obligation from already corroborated external metadata."""
import importlib.util
import os
from paper_compiler import fixed_r31
from paper_compiler_r31_fixtures import bind_type
from paper_compiler.programs import execute_pure
if os.environ.get("R31_ASSET_PATH"):
    spec=importlib.util.spec_from_file_location("paper_compiler.pages_candidate",os.environ["R31_ASSET_PATH"])
    fixed_r31=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixed_r31)

def check(*,identity=True,known_pages=True,pages_state="confirmed_absent",complete=True):
    external={"exists":{"state":"observed","value":True,"evidence_ids":["public-work"]} if identity else {"state":"unknown"},
              "available_fields":{"state":"observed","value":["pages"] if known_pages else ["title"],"evidence_ids":["public-pages"]}}
    payload={"ir":{"nodes":[{"id":"entry","kind":"BibliographyEntry","text":"AUTHOR A. A useful study[C]//Conference on Examples. 2020."}]},
             "analysis":{"coverage":{"entry":{"status":"complete" if complete else "partial"}},
             "results":{"bibliography_fields":{"entry":{"title":{"state":"observed","value":"A useful study"},"pages":{"state":pages_state,"value":"1-9" if pages_state=="observed" else None}}},
              "r31_source_context":{"entry":{"resource_kind":{"state":"observed","value":"conference","evidence_ids":["entry"]}}},
              "external_work":{"entry":external}}}}
    text=payload['ir']['nodes'][0]['text'];venue='Conference on Examples'
    fields=payload['analysis']['results']['bibliography_fields']['entry']
    start=text.index(venue)
    fields['container']={'state':'observed','value':venue,'source_range':[start,start+len(venue)],'evidence_ids':['entry']}
    if identity:
        bind_type(payload['analysis'],'entry',text,'conference',year='2020',year_start=text.index('2020'))
        if known_pages:payload['analysis']['evidence'][-1]['work']['pages']='1-9'
        external['available_fields']['evidence_ids']=['metadata-type-entry']
    return execute_pure(fixed_r31.build_r31_package()["code"],payload)[0]

def test_known_existing_pages_condition_uses_grounded_evidence():
    row=check()
    assert row["status"]=="VIOLATION"
    assert "metadata-type-entry" in row["evidence_ids"]
    assert "external_work" in fixed_r31.build_r31_package()["program_spec"]["requires"]

def test_unknown_identity_or_page_existence_never_becomes_required():
    for kwargs in [{"identity":False},{"known_pages":False},{"pages_state":"unknown"},{"pages_state":"observed"},{"complete":False}]:
        assert check(**kwargs)["status"]!="VIOLATION"
