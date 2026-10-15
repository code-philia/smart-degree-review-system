from pathlib import Path
from pdf_rules.model import PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import reconcile_physical_rasters

def obj(box,role):return LayoutObject('figure',1,box,'',600,840,role)
def run(objects,images,captions=()):
 doc=PdfDocument(Path('crop-evidence.pdf'),(PdfPage(1,600,840,(),images=tuple(images)),))
 return reconcile_physical_rasters(objects,list(captions),doc)

def test_cloud_crop_and_full_physical_image_are_one_object_even_without_title():
 physical=(80,100,240,340)
 objects=[obj(physical,'native_figure'),obj((100,135,236,354),'image_body')]
 result=run(objects,[physical])
 assert len(result)==1
 assert result[0].bbox==(80,100,240,354)

def test_large_cloud_region_owns_several_partially_cropped_physical_tiles():
 region=(110,120,490,310)
 images=[(80,105,180,220),(80,223,180,335),(410,105,510,220),(410,223,510,335)]
 objects=[obj(region,'image_body')]+[obj(b,'native_figure') for b in images]
 assert len(run(objects,images))==1

def test_overlapping_native_carrier_keeps_internal_independent_title_boundaries():
 physical=(80,100,500,350)
 objects=[obj(physical,'native_figure'),obj((100,135,280,330),'image_body'),obj((310,135,490,330),'image_body')]
 captions=[LayoutObject('figure_caption',1,(120,300,260,315),'Figure 2.1 First',600,840)]
 assert len(run(objects,[physical],captions))>=2

def test_small_picture_merely_near_a_cloud_figure_is_not_absorbed():
 objects=[obj((80,100,500,300),'image_body'),obj((100,315,150,350),'native_figure')]
 assert len(run(objects,[(100,315,150,350)]))==2
