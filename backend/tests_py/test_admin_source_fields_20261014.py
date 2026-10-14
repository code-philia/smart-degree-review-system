"""Real source pixels and independent frozen OCR for administrative field proof."""
import json
from dataclasses import replace
from pathlib import Path
from time import monotonic
from unittest.mock import patch
import numpy as np,pymupdf as f,pytest
from pdf_rules.local_ocr import OcrText
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.signature_structure import recover_structure,_decision_regions
P=Path(__file__).parent/'fixtures/admin_source_fields_20261014'
FACTS=json.loads((P/'observations.json').read_text())
def read(name):
 q=FACTS[name]
 with f.open(P/(name+'.pdf')) as d:
  pm=d[0].get_pixmap(matrix=f.Matrix(q['scale'],q['scale']),colorspace=f.csGRAY,alpha=False)
  gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
 hits=tuple(OcrText(**dict(h,bbox=tuple(h['bbox']))) for h in q['observations'])
 return gray,q['scale'],hits,tuple(q['derotation_matrix'])
def page(name,number=1):
 w,h=FACTS[name]['dimensions'];return PdfPage(number,w,h,(),unreadable=True,images=((0,0,w,h),))
def recover(name):
 p=page(name);d=PdfDocument(P/(name+'.pdf'),(p,))
 with patch('pdf_rules.signature_structure.display_read',return_value=read(name)):
  return recover_structure(d,None,p,monotonic()+30)
def covered(box,regions):
 return any(a<=box[0]+.5 and b<=box[1]+.5 and c>=box[2]-.5 and d>=box[3]-.5 for a,b,c,d in regions)
@pytest.mark.parametrize('name,box',[
 ('authorization_blank_expiry',(234,294.5,382.5,296.5)),
 ('authorization_far_adviser',(525.5,342,558.5,398.5)),
 ('authorization_weak_adviser',(333,658.5,563.5,709.5)),
 ('authorization_weak_adviser',(189.5,515.5,195.5,526)),
])
def test_actual_printed_administrative_field_owns_its_source_ink(name,box):
 answer=recover(name);assert answer is not None
 assert covered(box,answer[1]['administrative_display_regions']),answer[1]['outside_ink']
@pytest.mark.parametrize('name',['decision_old_grid','decision_compact_grid'])
def test_actual_decision_separate_vote_triplet_has_complete_source_schema(name):
 p=page(name);gray,scale,hits,_=read(name);details={}
 regions=_decision_regions(hits,p.width,p.height,gray,scale,details)
 assert regions,details
 assert details['committee_rows']==6 and details['signed_rows']>=3
@pytest.mark.parametrize('name',['decision_old_grid','decision_compact_grid'])
def test_vote_triplet_in_independent_review_prose_cannot_complete_schema(name):
 p=page(name);gray,scale,hits,_=read(name)
 hits=tuple(replace(h,bbox=(h.bbox[0],400,h.bbox[2],416)) if h.text.strip()=='5/5/5' or h.text.startswith('5/5/5') else h for h in hits)
 assert not _decision_regions(hits,p.width,p.height,gray,scale)
def test_continuing_signed_roster_can_read_previous_source_form_without_parser_table_guess():
 prev=page('decision_roster_previous');curr=page('decision_review_field',2);d=PdfDocument(P/'decision_roster_pair.pdf',(prev,curr));reads={1:read('decision_roster_previous'),2:read('decision_review_field')}
 with patch('pdf_rules.signature_structure.display_read',side_effect=lambda _d,p,_deadline:reads[p.number]):
  answer=recover_structure(d,prev,curr,monotonic()+30)
 assert answer is not None and answer[1]['kind']=='committee_continuation'
 assert answer[1]['previous_page']==1
 assert covered((73,96,524,231),answer[1]['administrative_display_regions'])
def test_continuing_roster_missing_previous_vote_schema_remains_unproved():
 prev=page('decision_roster_previous');curr=page('decision_review_field',2);d=PdfDocument(P/'decision_roster_pair.pdf',(prev,curr));r=read('decision_roster_previous');r=(r[0],r[1],tuple(h for h in r[2] if '投票表决结果' not in h.text),r[3]);reads={1:r,2:read('decision_review_field')}
 with patch('pdf_rules.signature_structure.display_read',side_effect=lambda _d,p,_deadline:reads[p.number]):answer=recover_structure(d,prev,curr,monotonic()+30)
 assert answer is None or answer[0] is None

@pytest.mark.parametrize('name',['authorization_blank_expiry','authorization_far_adviser','authorization_weak_adviser'])
def test_field_ownership_cannot_hide_independent_native_research(name):
 p=page(name);line=PdfLine(1,'实验结果说明该方法具有稳定的频率响应。',(420,367,553,382),p.width,p.height,source='native')
 p=replace(p,lines=(line,));d=PdfDocument(P/(name+'.pdf'),(p,))
 with patch('pdf_rules.signature_structure.display_read',return_value=read(name)):
  answer=recover_structure(d,None,p,monotonic()+30)
 assert answer is None or answer[0] is None

@pytest.mark.parametrize('kind',['photo','faint_photo','faint_reference'])
def test_new_signature_field_components_keep_separate_alpha_research_layer(tmp_path,kind):
 from PIL import Image
 import io
 name='authorization_far_adviser';path=tmp_path/'independent-field-layer.pdf';p=page(name)
 with f.open(P/(name+'.pdf')) as pdf:
  with f.open() as v:
   raw=v.new_page(width=p.width,height=p.height)
   if kind=='faint_reference':raw.insert_text((535,370),'Fig9.9',fontsize=6,color=(.99,)*3)
   else:raw.draw_rect((532,348,554,377),fill=(.99,)*3 if kind=='faint_photo' else (.4,.6,.2),color=None)
   pm=raw.get_pixmap(matrix=f.Matrix(3,3),colorspace=f.csRGB,alpha=False);rgb=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width,3).copy();alpha=(np.any(rgb<255,axis=2)*255).astype('uint8');encoded=io.BytesIO();Image.fromarray(np.dstack((rgb,alpha))).save(encoded,format='PNG')
  pdf[0].insert_image(pdf[0].rect,stream=encoded.getvalue(),keep_proportion=False);pdf.save(path)
 with f.open(path) as pdf:
  pm=pdf[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False);g=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
 r=read(name);d=PdfDocument(path,(p,))
 with patch('pdf_rules.signature_structure.display_read',return_value=(g,2,r[2],r[3])):answer=recover_structure(d,None,p,monotonic()+30)
 assert answer is None or answer[0] is None

def test_missing_adviser_full_page_proposal_gets_a_field_bounded_source_read():
 answer=recover('authorization_unrecognized_adviser');assert answer is not None
 assert covered((438.5,659.5,506.5,694.5),answer[1]['administrative_display_regions'])
def test_new_observed_public_checkbox_component_stays_owned():
 answer=recover('authorization_separate_checkbox');assert answer is not None
 assert covered((195.5,519,200,523),answer[1]['administrative_display_regions'])
