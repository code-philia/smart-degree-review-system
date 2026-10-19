"""Hand-authored format obligations through real extraction and sandbox."""
import importlib
import importlib.util
import pytest
from paper_compiler.pipeline import detect
from test_paper_compiler_program_analysis import paper
from paper_compiler.registry import FIELD_TYPES

def asset():
    assert importlib.util.find_spec("paper_compiler.fixed_r31"), "fixed R31 asset missing"
    return importlib.import_module("paper_compiler.fixed_r31").build_package()

class SourceFacts:
    config={"MAAS_MODEL":"fake","MAAS_MODEL_VERSION":"r31-fixture"}
    def __init__(self,fields,kind="journal_article",electronic=False):
        self.fields=fields;self.kind=kind;self.electronic=electronic
    def complete_json(self,task,instructions,data,max_tokens):
        if task=="bibliography-fields/1.1":
            return {"entries":[{"id":e["id"],"complete":True,
                "fields":{k:{"state":"observed","value":v,"quote":(v if isinstance(v,str) and v in e["text"] else v[0] if isinstance(v,list) and len(v)==1 and v[0] in e["text"] else e["text"])} for k,v in self.fields.items()},
                "absent":[k for k in FIELD_TYPES if k not in self.fields]} for e in data["entries"]]}
        raise AssertionError("fixed R31 must not request model genre classification")

def check(tmp_path,text,fields,kind="journal_article",electronic=False,verified=False):
    ir=paper(tmp_path)
    entry=next(n for n in ir["nodes"] if n["kind"]=="BibliographyEntry")
    entry["text"]=text;entry["provenance"]=[{"kind":"synthetic","operation_id":"format-fixture","ancestor_provenance":entry["provenance"]}]
    class PublicMetadata:
        providers=['fixture_public_catalog'];snapshot_id='fixture-metadata'
        def lookup(self,query):
            from paper_compiler_r31_fixtures import TYPES
            return [{'id':'public-type','provider':self.providers[0],'status':'ok','coverage':'partial_index',
                     'work':{**query,'type':TYPES[kind],'container':fields.get('container')}}]
    ir,a,r=detect(ir,[asset()],client=SourceFacts(fields,kind,electronic),gateway=PublicMetadata() if verified else None,cache_dir=tmp_path/"cache")
    return next(row for row in r["rules"][0]["results"] if row["node_id"]==entry["id"])

@pytest.mark.parametrize("text,fields",[
    ("[1] A study[J]",{"title":"A study","type_code":"J"}),
    ("[1] A study[J]. https://doi.org/10.1/thing",{"title":"A study","type_code":"J","url":"https://doi.org/10.1/thing"}),
    ("[1] A vio-\nlation study[J/OL]. https://example.org/item",{"title":"A vio-lation study","type_code":"J/OL","url":"https://example.org/item"}),
])
def test_optional_fields_doi_url_and_layout_are_not_universal_obligations(tmp_path,text,fields):
    row=check(tmp_path,text,fields)
    assert row['status']=='UNKNOWN'
    assert '实际文献类型未由同版本独立元数据确证' in row['message']

@pytest.mark.parametrize("text,fields",[
    ("[1] A study. Journal, 2020.",{"title":"A study","year":"2020"}),
    ("[1] A study[XX].",{"title":"A study","type_code":"XX"}),
    ("[1] A study[J/OL/OL].",{"title":"A study","type_code":"J/OL/OL"}),
    ("[1] A study[J][OL].",{"title":"A study","type_code":"J","carrier_code":"OL"}),
])
def test_missing_invalid_and_duplicate_markers_are_violations(tmp_path,text,fields):
    assert check(tmp_path,text,fields)["status"]=="VIOLATION"

def test_verified_resource_kind_conflict_without_title_memorization(tmp_path):
    row=check(tmp_path,"[1] AUTHOR A. An unfamiliar research study[M]. Journal, 2020.",
        {'authors':['AUTHOR A'],'title':'An unfamiliar research study','type_code':'M','year':'2020','container':'Journal'},verified=True)
    assert row['status']=='VIOLATION' and 'public-type' in row['evidence_ids']

def test_general_webpage_requires_access_date_but_unknown_genre_is_not_topic_inference(tmp_path):
    assert check(tmp_path,"[1] An item[EB/OL]. https://example.org/x",
        {"title":"An item","type_code":"EB/OL","url":"https://example.org/x"},kind="webpage",electronic=True)["status"]=="VIOLATION"

def test_substantive_duplicate_tail_year_not_conference_name_year(tmp_path):
    assert check(tmp_path,"[1] A study[J]. Journal, 2020, 4: 1-9. 2020.",
        {"title":"A study","type_code":"J","year":"2020","volume":"4","pages":"1-9"})["status"]=="VIOLATION"

def test_unresolved_real_resource_kind_does_not_create_conflict(tmp_path):
    row=check(tmp_path,"[1] A study[M].",{"title":"A study","type_code":"M"},kind=None)
    assert row["status"]!="VIOLATION"

def test_body_contiguous_range_and_automatic_numbering_unknown_exception(tmp_path):
    from paper_compiler.analysis import base_analysis,citation_syntax
    from paper_compiler.model_runtime import apply_model
    from paper_compiler.programs import run_program
    ir=paper(tmp_path);ir["nodes"][0]["children"].append("cg")
    ir["nodes"].append({"id":"cg","kind":"CitationGroup","text":"[22-23]","children":[],"attrs":{},
        "provenance":[{"kind":"synthetic","operation_id":"format-fixture","ancestor_provenance":[]}]})
    pkg=asset();ir=apply_model(ir,pkg["model"],client=None);a=base_analysis(ir);a["capability_versions"].update(pkg["manifest"]["capability_versions"]);citation_syntax(ir,a)
    assert next(r for r in run_program(pkg,ir,a) if r["node_id"]=="cg")["status"]=="PASS"
    ir["nodes"][-1]["text"]="[22,23]"
    a=base_analysis(ir);a["capability_versions"].update(pkg["manifest"]["capability_versions"]);citation_syntax(ir,a)
    assert next(r for r in run_program(pkg,ir,a) if r["node_id"]=="cg")["status"]!="VIOLATION"


def test_declared_online_carrier_requires_access_path_even_if_medium_unknown(tmp_path):
    row=check(tmp_path,"[1] A study[C/OL]//A Conference. 2020: 1-9.",
        {"title":"A study","type_code":"C/OL","year":"2020","pages":"1-9"},kind="conference",electronic=False)
    assert row['status']=='VIOLATION'


def test_online_doi_resolver_is_access_path_even_when_extractor_uses_doi_field(tmp_path):
    row=check(tmp_path,"[1] A study[C/OL]//A Conference. 2020: 1-9. https://doi.org/10.1109/abc.2020.1",
        {"title":"A study","type_code":"C/OL","year":"2020","doi":"10.1109/abc.2020.1"},kind="conference",electronic=False)
    assert row['status']=='UNKNOWN'
    assert '访问路径' not in row['message'] and '获取路径' not in row['message']


def test_complete_online_entry_without_any_path_is_not_hidden_by_unknown_url_field(tmp_path):
    from paper_compiler.programs import run_program
    ir=paper(tmp_path);entry=next(n for n in ir['nodes'] if n['kind']=='BibliographyEntry')
    entry['text']='[1] A study[C/OL]//A Conference. 2020: 1-9.'
    entry['provenance']=[{'kind':'synthetic','operation_id':'access-test','ancestor_provenance':entry['provenance']}]
    package=asset()
    ir,a,r=detect(ir,[package],client=SourceFacts({'title':'A study','type_code':'C/OL','year':'2020'},kind='conference'),gateway=None,cache_dir=tmp_path/'cache')
    a['results']['bibliography_fields']['entry']['url']={'state':'unknown','reason':'field not returned by extraction'}
    row=next(x for x in run_program(package,ir,a) if x['node_id']=='entry')
    assert row['status']=='VIOLATION'
