from dataclasses import replace
from pathlib import Path
import json,hashlib
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import recover_native_raster_partitions
from pdf_rules.layout_context import recover_document,prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
F=Path(__file__).parent/'fixtures/horizontal_native_caption_partition_20261014/actual13-067.json'
FACTS=json.loads(F.read_text())
def frozen(v):
 if isinstance(v,list):return tuple(frozen(q) for q in v)
 if isinstance(v,dict):return {k:frozen(q) for k,q in v.items()}
 return v
def actual(name):
 q=FACTS[name];p=Path(q['source_pdf'])
 if not p.exists():pytest.skip('original read-only source case unavailable')
 assert hashlib.sha256(p.read_bytes()).hexdigest()==q['source_pdf_sha256']
 values=frozen(q['native_page']);values['lines']=tuple(PdfLine(**line) for line in values['lines']);page=PdfPage(**values)
 objects=[LayoutObject(**frozen(v)) for v in q['raw_layout']]
 return PdfDocument(p,(page,)),objects
def test_actual13_067_caption_only_mutant_reports_only_the_untitled_left_source():
 document,raw=actual('mutant');prepared=prepare_caption_layout(raw,recover_document(document,raw));findings=detect_caption_rules(prepared,[13],document)['13']['findings']
 assert len(findings)==1
 b=findings[0]['location']['bounding_rect'];assert b['page_number']==15 and b['x2']<=282.1 and b['y1']>=374
 assert hashlib.sha256(document.path.read_bytes()).hexdigest()==FACTS['mutant']['source_pdf_sha256']
def test_actual13_067_mother_keeps_both_independent_captioned_sources():
 document,raw=actual('mother');prepared=prepare_caption_layout(raw,recover_document(document,raw))
 assert detect_caption_rules(prepared,[13],document)['13']['findings']==[]
 assert hashlib.sha256(document.path.read_bytes()).hexdigest()==FACTS['mother']['source_pdf_sha256']
def objects(*,gap=8,caption=(220,310,380,325),lines=()):
 images=((50,180,210,300),(210+gap,180,390,300));page=PdfPage(1,450,650,tuple(lines),images=images)
 body=LayoutObject('figure',1,(49,179,391,301),'',450,650,role='image_body')
 cap=LayoutObject('figure_caption',1,caption,'Fig. 2 Result',450,650)
 return PdfDocument(Path('/nonexistent-original.pdf'),(page,)),body,cap
def test_horizontal_caption_exclusively_supporting_one_source_preserves_two_obligations():
 document,body,cap=objects();targets=recover_native_raster_partitions([body],document,[cap])
 assert len(targets)==2 and all(t.role=='native_raster_partition' for t in targets)
 assert detect_caption_rules(targets+[cap],[13],document)['13']['findings'][0]['location']['bounding_rect']['x2']==210
def test_abutting_original_tiles_are_not_split_by_a_localized_title():
 document,body,cap=objects(gap=0)
 assert recover_native_raster_partitions([body],document,[cap])==[body]
def test_common_wide_caption_keeps_a_composite_raster_envelope():
 document,body,cap=objects(caption=(60,310,380,325))
 assert recover_native_raster_partitions([body],document,[cap])==[body]
def test_complete_native_panel_sequence_keeps_its_common_caption_namespace():
 lines=(PdfLine(1,'(a)',(120,283,133,298),450,650),PdfLine(1,'(b)',(300,283,313,298),450,650))
 document,body,cap=objects(lines=lines)
 assert recover_native_raster_partitions([body],document,[cap])==[body]
def test_explicit_left_right_role_caption_keeps_its_declared_composite():
 document,body,cap=objects();cap=replace(cap,text='Fig. 2 (left) original; (right) reconstruction')
 assert recover_native_raster_partitions([body],document,[cap])==[body]
def test_oversized_cloud_rectangle_is_not_reclassified_from_two_partial_sources():
 document,body,cap=objects();body=replace(body,bbox=(10,170,430,302))
 assert recover_native_raster_partitions([body],document,[cap])==[body]


def test_short_common_caption_centered_on_unequal_original_tiles_keeps_one_figure():
    images=((50,180,350,300),(350.4,180,400,300))
    caption=LayoutObject('figure_caption',1,(175,329,275,344),'Fig. 2 Common tiled image',450,650)
    body=LayoutObject('figure',1,(50,180,400,300),'',450,650,role='image_body')
    document=PdfDocument(Path('/nonexistent-centered-tiled-original.pdf'),(PdfPage(1,450,650,(),images=images),))
    prepared=prepare_caption_layout([body,caption],recover_document(document,[body,caption]))
    assert detect_caption_rules(prepared,[13],document)['13']['findings']==[]
    assert len([obj for obj in prepared if obj.kind=='figure'])==1
