"""Original source pixels, exact transforms and adverse research-ink cases."""
from pathlib import Path
import json,hashlib
from dataclasses import replace
import numpy as np,pytest
from PIL import Image
from pdf_rules.local_ocr import OcrText
from pdf_rules.scan_boundary_proof import prove_continuous_source_boundary,prove_signed_form_barcode,exact_contiguous_source_partitions,prove_contiguous_paper_boundary
P=Path(__file__).parent/'fixtures/scan_boundary_proof_20261014'
FACTS={q['name']:q for q in json.loads((P/'source-observations.json').read_text())}
def source(name):
 q=FACTS[name];a=np.asarray(Image.open(P/(name+'.png')).convert('L'))
 assert hashlib.sha256(a.tobytes()).hexdigest()==q['source_pixel_sha256']
 return a,dict(source_bbox=q['source_bbox'],source_to_display=q['source_to_display'],page_bbox=q['page_bbox'])
def barcode(name,**changes):
 a,k=source(name);q=FACTS[name];k.update(observations=tuple(OcrText(**dict(h,bbox=tuple(h['bbox']))) for h in q['observations']),decision_schema_proof=q['decision_schema_proof']);k.update(changes)
 return prove_signed_form_barcode(a,**k)
def boundary(a=None,**changes):
 original,k=source('declaration_boundary_rotated');k.update(guard=(593.5,0,595.5,842),guard_kind='_GraphicGuard',display_sample_pitch=.5);k.update(changes)
 return prove_continuous_source_boundary(original if a is None else a,**k)
@pytest.mark.parametrize('name',['decision_barcode_high','decision_barcode_low','decision_barcode_compact'])
def test_actual_shifted_header_bars_match_independently_paired_student_id(name):
 p=barcode(name);assert p is not None
 assert p['parallel_bar_count']>=12 and p['paired_student_id']
 assert p['label_bbox'][1]>p['bar_bbox'][1]
 assert p['source_pixel_sha256']==FACTS[name]['source_pixel_sha256']
def test_actual_gray_rotated_physical_edge_gets_exact_component_proof():
 p=boundary();assert p is not None
 assert p['source_edge']=='top' and p['whole_edge_coverage']==1
 assert p['maximum_component_depth_points']<=2
 assert p['source_pixel_sha256']==FACTS['declaration_boundary_rotated']['source_pixel_sha256']
def test_exact_binary_boundary_has_the_same_source_component_obligation():
 a=np.full((1000,800),255,np.uint8);a[:2]=0
 p=prove_continuous_source_boundary(a,source_bbox=(0,0,400,500),source_to_display=(400,0,0,500,0,0),page_bbox=(0,0,400,500),guard=(0,0,400,1),guard_kind='_VisibleInkGuard',display_sample_pitch=.5)
 assert p is not None and p['source_edge']=='top'
@pytest.mark.parametrize('kind',['_TextGuard','_IndependentInkGuard','tuple'])
def test_independent_text_or_layer_guard_cannot_borrow_source_boundary(kind):
 assert boundary(guard_kind=kind) is None
def test_body_stem_attached_anywhere_to_the_edge_vetoes_a_partial_guard():
 a,_=source('declaration_boundary_rotated');a=a.copy();a[:35,1000:1004]=0
 assert boundary(a,guard=(593.5,0,595.5,250)) is None
def test_disconnected_body_line_entering_boundary_normal_band_is_retained():
 a,_=source('declaration_boundary_rotated');a=a.copy();a[5,700:800]=0
 assert boundary(a) is None
def test_thin_partial_graphic_line_cannot_borrow_a_physical_edge():
 a,_=source('declaration_boundary_rotated');a=np.full_like(a,255);a[0,:a.shape[1]//2]=0
 assert boundary(a) is None
def test_foreground_alpha_layer_cannot_borrow_opaque_scan_boundary():
 a,_=source('declaration_boundary_rotated');alpha=np.full(a.shape,255,np.uint8);alpha[0,100:200]=0
 assert boundary(alpha=alpha) is None
def test_unrelated_native_or_independent_layer_region_keeps_its_veto():
 assert boundary(independent_regions=((594,300,595,302),)) is None
def test_guard_rounding_beyond_one_display_pixel_is_not_owned():
 assert boundary(guard=(593.5,0,596,842)) is None
def test_boundary_requires_the_original_source_transform_not_a_crop_guess():
 q=FACTS['declaration_boundary_rotated'];b=q['source_bbox'];assert boundary(source_bbox=(b[0]+1,b[1],b[2],b[3])) is None
@pytest.mark.parametrize('name',['decision_barcode_high','decision_barcode_low','decision_barcode_compact'])
def test_bars_without_independently_completed_signed_form_remain_ink(name):
 assert barcode(name,decision_schema_proof={}) is None
def test_mismatched_header_id_is_not_a_proved_administrative_barcode():
 name='decision_barcode_high';q=FACTS[name];hits=tuple(OcrText(**dict(h,bbox=tuple(h['bbox']))) for h in q['observations']);hits=tuple(replace(h,text='123456789012') if h.text=='015072910035' and h.bbox[0]>400 else h for h in hits)
 assert barcode(name,observations=hits) is None
def test_complete_form_does_not_own_bars_relocated_into_body():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];t=list(k['source_to_display']);t[5]+=300;k['source_to_display']=t;b=list(k['source_bbox']);b[1]+=300;b[3]+=300;k['source_bbox']=b
 hits=tuple(OcrText(**dict(h,bbox=tuple(h['bbox']))) for h in q['observations']);hits=tuple(replace(h,bbox=(h.bbox[0],h.bbox[1]+300,h.bbox[2],h.bbox[3]+300)) if h.text=='015072910035' and h.bbox[0]>400 else h for h in hits)
 assert prove_signed_form_barcode(a,**k,observations=hits,decision_schema_proof=q['decision_schema_proof']) is None

def test_visible_ink_outside_the_measured_edge_component_is_not_owned():
 assert boundary(guard=(585,100,595.5,150)) is None

def test_barcode_with_independent_alpha_pixels_keeps_its_veto():
 a,_=source('decision_barcode_high');alpha=np.full(a.shape,255,np.uint8);alpha[100,1200]=0
 assert barcode('decision_barcode_high',alpha=alpha) is None

def test_numeric_label_cannot_own_independent_native_region():
 p=barcode('decision_barcode_high');assert p is not None
 assert barcode('decision_barcode_high',independent_regions=(p['label_bbox'],)) is None

def test_bar_group_guard_cannot_hide_an_attached_body_glyph():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];p=barcode('decision_barcode_high');a=a.copy()
 x,y,z,d=p['source_bar_pixel_boxes'][len(p['source_bar_pixel_boxes'])//2];a[d-1:d+35,x:x+2]=0
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=p['bar_bbox']) is None

def test_actual_bar_pixels_copied_into_body_keep_their_research_obligation():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];p=barcode('decision_barcode_high');a=a.copy();h,w=a.shape;t=q['source_to_display']
 left=min(p['bar_bbox'][0],p['label_bbox'][0]);top=p['bar_bbox'][1];right=max(p['bar_bbox'][2],p['label_bbox'][2]);bottom=p['label_bbox'][3]
 x=int((left-t[4])/t[0]*w);z=int((right-t[4])/t[0]*w)+1;y=int((top-t[5])/t[3]*h);d=int((bottom-t[5])/t[3]*h)+1;dy=round(300/t[3]*h)
 patch=a[y:d,x:z].copy();a[y:d,x:z]=255;a[y+dy:d+dy,x:z]=patch
 hits=tuple(OcrText(**dict(v,bbox=tuple(v['bbox']))) for v in q['observations']);hits=tuple(replace(v,bbox=(v.bbox[0],v.bbox[1]+300,v.bbox[2],v.bbox[3]+300)) if v.text==p['paired_student_id'] and v.bbox[0]>400 else v for v in hits)
 assert prove_signed_form_barcode(a,**k,observations=hits,decision_schema_proof=q['decision_schema_proof']) is None


def actual_strip_views():
 q=json.loads((P/'actual-strip-views.json').read_text())
 return q,[dict(v,pixels=np.asarray(Image.open(P/v['fixture']).convert('L'))) for v in q['views']]

def test_exact_original_header_partitions_keep_mismatched_last_density_separate():
 q,views=actual_strip_views();parts=exact_contiguous_source_partitions(views)
 assert len(parts)==1 and parts[0]['source_indices']==list(range(8))
 assert parts[0]['resampled'] is False and parts[0]['maximum_join_roundoff_points']<.0001
 assert np.array_equal(parts[0]['pixels'],np.concatenate([v['pixels'] for v in views[:8]],axis=0))
 p=parts[0];proof=prove_signed_form_barcode(p['pixels'],source_bbox=p['source_bbox'],source_to_display=p['source_to_display'],page_bbox=q['page_bbox'],observations=FACTS['decision_barcode_low']['observations'],decision_schema_proof=FACTS['decision_barcode_low']['decision_schema_proof'])
 assert proof is not None

def test_real_strip_gap_is_not_silently_filled_or_resampled():
 _,views=actual_strip_views();views=views[:2];b=list(views[1]['source_bbox']);b[1]+=1;b[3]+=1;t=list(views[1]['source_to_display']);t[5]+=1;views[1]=dict(views[1],source_bbox=b,source_to_display=t)
 assert not exact_contiguous_source_partitions(views)

def test_mismatched_strip_source_density_cannot_be_resampled_to_fit():
 _,views=actual_strip_views();assert not exact_contiguous_source_partitions(views[-2:])

def test_coincident_duplicate_layers_do_not_form_an_ambiguous_partition():
 _,views=actual_strip_views();assert not exact_contiguous_source_partitions([views[0],views[1],views[1]])

def test_partial_source_partition_is_not_a_complete_physical_paper_boundary():
 a=np.full((900,800),255,np.uint8);a[:2]=0
 assert prove_continuous_source_boundary(a,source_bbox=(0,0,400,450),source_to_display=(400,0,0,450,0,0),page_bbox=(0,0,400,500),guard=(0,0,400,1),guard_kind='_GraphicGuard',display_sample_pitch=.5) is None


def test_barcode_display_roundoff_cannot_be_used_as_a_broad_halo():
 assert barcode('decision_barcode_high',guard=(430,40,560,110),display_sample_pitch=100) is None

def test_clipped_source_bars_cannot_own_numeric_label_from_outside_that_source():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];p=barcode('decision_barcode_high');t=list(k['source_to_display']);cut=int((p['label_bbox'][1]-t[5])/t[3]*a.shape[0])+1;t[3]=t[3]*cut/a.shape[0];b=list(k['source_bbox']);b[3]=t[5]+t[3]
 assert prove_signed_form_barcode(a[:cut],source_bbox=b,source_to_display=t,page_bbox=k['page_bbox'],observations=q['observations'],decision_schema_proof=q['decision_schema_proof']) is None


@pytest.mark.parametrize('name,guard',[
 ('decision_barcode_high',(454.5,42.5,545,93)),
 ('decision_barcode_compact',(463.5,45.5,543,87)),
])
def test_actual_bar_guards_are_owned_by_measured_original_visible_soft_components(name,guard):
 p=barcode(name,guard=guard);assert p is not None
 assert p['source_visible_bar_components'] and p['hard128_bar_bbox']

def test_bar_soft_component_cannot_own_attached_body_glyph_above_the_core_threshold():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];p=barcode('decision_barcode_high');a=a.copy();x,y,z,d=p['source_bar_pixel_boxes'][len(p['source_bar_pixel_boxes'])//2];a[d-1:d+8,x:x+2]=220
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof']) is None

def test_bar_soft_component_cannot_own_foreign_visible_ink_in_a_bar_gap():
 a,k=source('decision_barcode_high');q=FACTS['decision_barcode_high'];p=barcode('decision_barcode_high');a=a.copy();boxes=sorted(p['source_bar_pixel_boxes']);left,right=max(zip(boxes,boxes[1:]),key=lambda t:t[1][0]-t[0][2]);x=(left[2]+right[0])//2;y=left[1]+30;a[y:y+6,x:x+2]=220
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof']) is None

def paper_boundary(views=None,**changes):
 q,actual=actual_strip_views();kw=dict(page_bbox=q['page_bbox'],guard=(592.5,10,594,832),guard_kind='_VisibleInkGuard',display_sample_pitch=.5);kw.update(changes)
 return prove_contiguous_paper_boundary(actual if views is None else views,**kw)

def test_actual_nine_plane_different_pitch_whole_physical_edge_has_exact_pixel_proof():
 p=paper_boundary();assert p is not None
 assert p['paper_group_coverage_fraction']>=.95 and p['source_plane_count']==9
 assert p['maximum_component_depth_points']<=2 and p['display_edge']=='right'
 assert all(v['whole_edge_coverage']==1 for v in p['source_planes'])

def test_actual_eight_plus_last_partition_preserves_each_different_pitch_plane():
 q,views=actual_strip_views();part=exact_contiguous_source_partitions(views)[0];v0={k:part[k] for k in ('pixels','source_bbox','source_to_display')};p=paper_boundary([v0,views[8]]);assert p is not None
 assert p['source_plane_count']==2 and p['source_planes'][1]['source_pixel_sha256']==views[8]['source_pixel_sha256']

def test_eight_plane_partial_paper_cannot_create_a_complete_edge():
 _,views=actual_strip_views();part=exact_contiguous_source_partitions(views)[0];v0={k:part[k] for k in ('pixels','source_bbox','source_to_display')}
 assert paper_boundary([v0],guard=(592.5,10,594,741)) is None

def test_actual_partial_top_source_edge_remains_unproved():
 assert paper_boundary(guard=(94,10,511.5,11)) is None

@pytest.mark.parametrize('delta',[-1,1])
def test_original_paper_group_gap_or_overlap_cannot_be_hidden(delta):
 _,views=actual_strip_views();b=list(views[4]['source_bbox']);b[1]+=delta;b[3]+=delta;t=list(views[4]['source_to_display']);t[5]+=delta;views[4]=dict(views[4],source_bbox=b,source_to_display=t)
 assert paper_boundary(views) is None

def test_attached_body_stem_on_another_plane_vetoes_a_partial_guard():
 _,views=actual_strip_views();a=views[6]['pixels'].copy();a[100:104,-35:]=0;views[6]=dict(views[6],pixels=a)
 assert paper_boundary(views,guard=(592.5,10,594,200)) is None

def test_partial_graphic_on_any_plane_cannot_borrow_the_whole_paper_edge():
 _,views=actual_strip_views();a=np.full_like(views[5]['pixels'],255);a[:a.shape[0]//2,-1]=0;views[5]=dict(views[5],pixels=a)
 assert paper_boundary(views) is None

def test_independent_alpha_plane_cannot_borrow_a_paper_partition_edge():
 _,views=actual_strip_views();alpha=np.full_like(views[8]['pixels'],255);alpha[0,0]=0;views[8]=dict(views[8],alpha=alpha)
 assert paper_boundary(views) is None

def test_independent_native_region_preserves_its_paper_edge_veto():
 assert paper_boundary(independent_regions=((592.8,700,593.5,704),)) is None

@pytest.mark.parametrize('kind',['_TextGuard','_IndependentInkGuard','tuple'])
def test_nonvisible_guard_cannot_inherit_paper_partition_boundary(kind):
 assert paper_boundary(guard_kind=kind) is None


def test_disconnected_body_line_inside_exact_proven_band_on_another_plane_is_retained():
 _,views=actual_strip_views();a=views[6]['pixels'].copy();a[100:106,-6]=0;views[6]=dict(views[6],pixels=a)
 assert paper_boundary(views,guard=(592.5,10,594,200)) is None


def test_barcode_cannot_claim_a_gray246_body_stem_outside_its_measured_source():
 a,k=source('decision_barcode_compact');q=FACTS['decision_barcode_compact'];p=barcode('decision_barcode_compact');a=a.copy();x,y,z,d=p['source_bar_pixel_boxes'][-1];a[d-1:d+20,z-2:z]=246
 t=q['source_to_display'];h,w=a.shape;guard=(p['bar_bbox'][0],p['bar_bbox'][1],p['bar_bbox'][2],t[5]+t[3]*(d+20)/h)
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=guard) is None

def test_gray246_independent_glyph_near_the_bars_keeps_its_own_source_guard():
 a,k=source('decision_barcode_compact');q=FACTS['decision_barcode_compact'];p=barcode('decision_barcode_compact');a=a.copy();x,y,z,d=p['source_bar_pixel_boxes'][-1];a[y+30:y+50,z+5:z+7]=246
 t=q['source_to_display'];h,w=a.shape;glyph=(t[4]+t[0]*(z+5)/w,t[5]+t[3]*(y+30)/h,t[4]+t[0]*(z+7)/w,t[5]+t[3]*(y+50)/h)
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=glyph) is None


def fringe(a,point):
 import cv2
 from pdf_rules.scan_boundary_proof import _measure_strict_bar_fringe
 _,labels,parts,_=cv2.connectedComponentsWithStats((a<=225).astype('uint8'),8)
 own=int(labels[point]);assert own
 x,y,w,h,_=map(int,parts[own])
 return _measure_strict_bar_fringe(a,labels,own,(x,y,w,h),paper=int(np.bincount(a.ravel(),minlength=256).argmax()))

def test_one_original_pixel_connected_soft_fringe_uses_actual_component_tree():
 a=np.full((70,70),255,np.uint8);a[10:50,30:34]=0;a[10:50,34]=243
 p=fringe(a,(20,31));assert p['source_box']==[30,10,5,40]
 assert p['chosen_source_level']==243 and p['source_paper_level']==255
 assert p['maximum_extension_pixels']==1 and p['entire_component_proved'] is True

def test_gray246_attached_body_stem_stops_fringe_before_body_ownership():
 a=np.full((70,70),255,np.uint8);a[10:50,30:34]=0;a[49:59,32:34]=246
 p=fringe(a,(20,31));assert p['source_box']==[30,10,4,40]
 assert p['chosen_source_level']<246 and p['topology_stop_source_level']==246
 assert p['topology_stop_reason'] in {'one_source_pixel_limit','sentinel_escape'}

def test_soft_fringe_cannot_merge_a_foreign_visible_core():
 a=np.full((70,70),255,np.uint8);a[10:50,30:34]=0;a[20:25,35]=200;a[20:25,34]=246
 p=fringe(a,(20,31));assert p['source_box']==[30,10,4,40]
 assert p['chosen_source_level']<246 and p['topology_stop_source_level']==246
 assert p['topology_stop_reason'] in {'foreign_visible_core','one_source_pixel_limit','sentinel_escape'}

def test_detached_gray246_island_in_core_box_is_not_part_of_its_fringe():
 a=np.full((70,70),255,np.uint8);a[10:50,30]=0;a[10:50,34]=0;a[10,30:35]=0;a[49,30:35]=0;a[25:28,32]=246
 p=fringe(a,(20,30));assert p['chosen_source_level']<246
 assert p['topology_stop_reason']=='independent_source_ink'

def test_compact_right_bar_last_valid_level_is_stopped_by_source_topology():
 a,_=source('decision_barcode_compact');p=fringe(a,(240,2255))
 assert p['source_box']==[2250,189,11,173]
 assert p['chosen_source_level']==246 and p['topology_stop_source_level']==247
 assert p['topology_stop_reason'] in {'foreign_visible_core','one_source_pixel_limit','sentinel_escape'}


def test_independent_gray246_source_guard_inside_bar_group_gap_cannot_borrow_group_bbox():
 a,k=source('decision_barcode_compact');q=FACTS['decision_barcode_compact'];p=barcode('decision_barcode_compact');a=a.copy();boxes=sorted(p['source_bar_pixel_boxes']);left,right=max(zip(boxes,boxes[1:]),key=lambda t:t[1][0]-t[0][2]);x=(left[2]+right[0])//2;y=left[1]+30;a[y:y+6,x:x+2]=246
 t=q['source_to_display'];h,w=a.shape;guard=(t[4]+t[0]*x/w,t[5]+t[3]*y/h,t[4]+t[0]*(x+2)/w,t[5]+t[3]*(y+6)/h)
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=guard) is None


@pytest.mark.parametrize('name',['decision_barcode_high','decision_barcode_low','decision_barcode_compact'])
def test_actual_entire_bar_group_guards_preserve_measured_source_controls(name):
 p=barcode(name);assert p is not None
 assert barcode(name,guard=p['bar_bbox']) is not None

@pytest.mark.parametrize('level',[230,240,246,248])
def test_entire_bar_group_guard_cannot_hide_an_unowned_weak_source_glyph(level):
 a,k=source('decision_barcode_compact');q=FACTS['decision_barcode_compact'];p=barcode('decision_barcode_compact');a=a.copy();boxes=sorted(p['source_bar_pixel_boxes']);left,right=max(zip(boxes,boxes[1:]),key=lambda t:t[1][0]-t[0][2]);x=(left[2]+right[0])//2;y=left[1]+30;a[y:y+6,x:x+2]=level
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=p['bar_bbox']) is None


def test_entire_bar_guard_keeps_a_coherent_mixed_tone_weak_glyph_obligation():
 a,k=source('decision_barcode_compact');q=FACTS['decision_barcode_compact'];p=barcode('decision_barcode_compact');a=a.copy();boxes=sorted(p['source_bar_pixel_boxes']);left,right=max(zip(boxes,boxes[1:]),key=lambda t:t[1][0]-t[0][2]);x=(left[2]+right[0])//2;y=left[1]+30;a[y:y+6,x:x+2]=np.tile(np.array([240,248],np.uint8),(6,1))
 assert prove_signed_form_barcode(a,**k,observations=q['observations'],decision_schema_proof=q['decision_schema_proof'],guard=p['bar_bbox']) is None
