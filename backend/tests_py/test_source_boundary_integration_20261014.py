"""Integrate original physical boundary and measured signed-form barcode proofs."""
import hashlib,json
from pathlib import Path
from dataclasses import replace
import numpy as np,pymupdf as f,pytest
from PIL import Image
from pdf_rules.model import PdfDocument,PdfPage
from pdf_rules.local_ocr import OcrText
from pdf_rules.signature_structure import _decision_regions
from pdf_rules.signature_source_artifacts import source_artifacts
from pdf_rules.scan_boundary_proof import prove_signed_form_barcode
P=Path(__file__).parent/'fixtures/scan_boundary_proof_20261014'
FACTS={q['name']:q for q in json.loads((P/'source-observations.json').read_text())}
class _GraphicGuard(tuple):pass
class _VisibleInkGuard(tuple):pass
class _TextGuard(tuple):pass
def original(name):
 q=FACTS[name];path=Path(q['source'])
 with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==q['source_sha256']
 with f.open(path) as pdf:
  raw=pdf[q['physical_page']-1];w,h=raw.mediabox.width,raw.mediabox.height;rotation=raw.rotation
 return q,PdfDocument(path,()),PdfPage(q['physical_page'],w,h,(),unreadable=True,display_rotation=rotation)
def barcode_input(name):
 q,doc,page=original(name)
 hits=tuple(OcrText(**dict(h,bbox=tuple(h['bbox']))) for h in q['observations'])
 with f.open(doc.path) as pdf:
  raw=pdf[page.number-1];pm=raw.get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
  gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
  regions=_decision_regions(hits,raw.rect.width,raw.rect.height,gray,2)
 assert regions
 pixels=np.asarray(Image.open(P/(name+'.png')).convert('L'))
 proof=prove_signed_form_barcode(pixels,source_bbox=q['source_bbox'],source_to_display=q['source_to_display'],page_bbox=q['page_bbox'],observations=hits,decision_schema_proof=q['decision_schema_proof'])
 assert proof is not None
 guards=[_GraphicGuard(proof['bar_bbox']),_TextGuard(proof['label_bbox'])]
 return q,doc,page,regions,hits,guards
@pytest.mark.parametrize('name',['decision_barcode_high','decision_barcode_low','decision_barcode_compact'])
def test_original_shifted_barcode_guards_are_owned_by_exact_signed_source(name):
 q,doc,page,regions,hits,guards=barcode_input(name)
 kept,proofs=source_artifacts(doc,page,regions,guards,observations=hits,decision_schema_proof=q['decision_schema_proof'],display_sample_pitch=.5)
 assert kept==[],[list(g) for g in kept]
 assert sum(p['kind']=='source_parallel_bars_paired_signed_form_id' for p in proofs)>=2
 if name=='decision_barcode_low':
  joins=[p for p in proofs if p['kind']=='exact_contiguous_original_source_partition']
  assert any(len(p['xrefs'])==8 and p['resampled'] is False for p in joins)
def test_original_grayscale_full_edge_guard_is_owned_by_actual_source():
 q,doc,page=original('declaration_boundary_rotated')
 guards=[_GraphicGuard((593.5,0,595.5,842))]
 kept,proofs=source_artifacts(doc,page,[(0,0,593.4,841.68)],guards,display_sample_pitch=.5)
 assert kept==[],kept
 assert any(p['kind']=='source_continuous_physical_boundary' for p in proofs)
def test_original_matching_id_cannot_own_a_body_graphic_guard():
 q,doc,page,regions,hits,_=barcode_input('decision_barcode_high')
 guard=_GraphicGuard((100,500,130,520))
 kept,_=source_artifacts(doc,page,regions,[guard],observations=hits,decision_schema_proof=q['decision_schema_proof'],display_sample_pitch=.5)
 assert guard in kept
def test_mismatching_barcode_observation_keeps_the_actual_source_guard():
 q,doc,page,regions,hits,guards=barcode_input('decision_barcode_high')
 hits=tuple(replace(h,text='123456789012') if h.text=='015072910035' and h.bbox[0]>400 else h for h in hits)
 kept,_=source_artifacts(doc,page,regions,guards,observations=hits,decision_schema_proof=q['decision_schema_proof'],display_sample_pitch=.5)
 assert len(kept)>=len(guards)


def test_original_different_pitch_paper_tiles_keep_whole_right_boundary_proof():
 q,doc,page=original("decision_barcode_low")
 guard=_VisibleInkGuard((592.5,10,594,832))
 kept,proofs=source_artifacts(doc,page,[],[guard],display_sample_pitch=.5)
 assert kept==[],[list(g) for g in kept]
 proof=next(p for p in proofs if p["kind"]=="source_contiguous_paper_physical_boundary")
 assert proof["source_plane_count"]==2 and proof["resampled"] is False

def test_source_integration_cannot_own_independent_gray_glyph_in_bar_gap(tmp_path):
 from io import BytesIO
 q,_,_,regions,hits,_=barcode_input("decision_barcode_compact")
 a=np.asarray(Image.open(P/"decision_barcode_compact.png").convert("L")).copy()
 p=prove_signed_form_barcode(a,source_bbox=q["source_bbox"],source_to_display=q["source_to_display"],page_bbox=q["page_bbox"],observations=hits,decision_schema_proof=q["decision_schema_proof"])
 boxes=sorted(p["source_bar_pixel_boxes"])
 left,right=max(zip(boxes,boxes[1:]),key=lambda t:t[1][0]-t[0][2])
 x=(left[2]+right[0])//2;y=left[1]+30
 a[y:y+6,x:x+2]=246
 t=q["source_to_display"];h,w=a.shape
 guard=_GraphicGuard((t[4]+t[0]*x/w,t[5]+t[3]*y/h,t[4]+t[0]*(x+2)/w,t[5]+t[3]*(y+6)/h))
 path=tmp_path/"source-independent-bar-gap.pdf";encoded=BytesIO();Image.fromarray(a).save(encoded,format="PNG")
 with f.open() as pdf:
  raw=pdf.new_page(width=q["page_bbox"][2],height=q["page_bbox"][3])
  raw.insert_image(q["source_bbox"],stream=encoded.getvalue(),keep_proportion=False)
  pdf.save(path)
 doc=PdfDocument(path,());page=PdfPage(1,q["page_bbox"][2],q["page_bbox"][3],(),unreadable=True)
 kept,proofs=source_artifacts(doc,page,regions,[guard],observations=hits,decision_schema_proof=q["decision_schema_proof"],display_sample_pitch=.5)
 assert guard in kept,proofs
