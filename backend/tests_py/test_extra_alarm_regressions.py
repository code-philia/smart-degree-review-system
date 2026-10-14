"""Directory continuation and empty-gap native table regressions."""
from pathlib import Path
import unittest
import pymupdf
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.native_layout import three_line_tables

class WrappedDirectoryTests(unittest.TestCase):
 def line(self,page,text,y,x=60,x2=520):
  return PdfLine(page,text,(x,y,x2,y+12),600,800)
 def document(self,kind):
  word='图' if kind=='figure' else '表'
  page1=PdfPage(1,600,800,(
   self.line(1,word+'1.1 短目录条目........2',130),
   self.line(1,word+'2.4 一个很长的目录标题，含有额外说明',160),
   self.line(1,'后续说明........24',180,x=90),
   self.line(1,word+'2.5 另一个条目........25',210),))
  page2=PdfPage(2,600,800,(self.line(2,word+'2.4 真正的正文图表标题',350,x=180,x2=450),))
  return PdfDocument(Path('paper.pdf'),(page1,page2))
 def test_wrapped_figure_directory_does_not_produce_duplicate_rule15_alarm(self):
  result=detect_rules(build_index(self.document('figure')),[15])['15']['findings']
  self.assertEqual([(f['page'],f['token']) for f in result],[(2,'2.4')])
 def test_wrapped_directory_handles_full_width_leaders_and_page_digits(self):
  lines=(self.line(1,'图2.4 长目录标题',130),self.line(1,'后续说明．．．．２４',150,x=90))
  d=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
  self.assertEqual(detect_rules(build_index(d),[15])['15']['findings'],[])
 def test_wrapped_table_directory_does_not_produce_duplicate_rule16_alarm(self):
  result=detect_rules(build_index(self.document('table')),[16])['16']['findings']
  self.assertEqual([(f['page'],f['token']) for f in result],[(2,'2.4')])
 def test_wrapped_directory_is_not_a_cloud_caption_for_nearby_object(self):
  d=self.document('figure')
  objects=[LayoutObject('figure',1,(80,60,510,150),'',600,800,role='image_body')]
  r=detect_caption_rules(prepare_caption_layout(objects,d),[13],d)['13']['findings']
  self.assertEqual(len(r),1)
 def test_directory_mentions_do_not_count_as_real_body_references(self):
  d=self.document('figure');p=d.pages[0]
  lines=(self.line(1,'图2.4 与图8.8对照的目录项',160),self.line(1,'说明........24',180,x=90))
  actual=PdfPage(2,600,800,(self.line(2,'图8.8 实际结果',350),))
  r=detect_rules(build_index(PdfDocument(d.path,(PdfPage(1,600,800,lines),actual))),[15])['15']['findings']
  self.assertEqual([(f['page'],f['token']) for f in r],[(2,'8.8')])
 def test_unrelated_distant_leader_does_not_hide_real_caption(self):
  lines=(self.line(1,'图9.9 实际图题',120),self.line(1,'其他内容........45',310))
  d=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
  self.assertEqual([f['token'] for f in detect_rules(build_index(d),[15])['15']['findings']],['9.9'])
 def test_real_caption_following_directory_on_same_page_is_kept(self):
  lines=(self.line(1,'图1.1 目录长标题',100),self.line(1,'后续........8',120,x=90),self.line(1,'图9.9 实际图题',250,x=170))
  d=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
  self.assertEqual([f['token'] for f in detect_rules(build_index(d),[15])['15']['findings']],['9.9'])
 def test_continuation_does_not_cross_into_a_new_numbered_entry(self):
  lines=(self.line(1,'图9.9 实际图题',120),self.line(1,'图1.1 目录条目........8',140))
  d=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
  self.assertEqual([f['token'] for f in detect_rules(build_index(d),[15])['15']['findings']],['9.9'])

class NativeEmptyGapTests(unittest.TestCase):
 def page(self):
  doc=pymupdf.open();self.addCleanup(doc.close);page=doc.new_page(width=600,height=800)
  for y in (150,170,230,250,290,310,380):page.draw_line((60,y),(520,y))
  for text,y in [('Header',165),('first body',215),('last row',245),('Lower header',305),('lower body',350)]:page.insert_text((70,y),text,fontsize=10)
  return page
 def test_empty_gap_between_tables_is_not_an_additional_table(self):
  boxes=three_line_tables(self.page())
  self.assertNotIn((60.,230.,520.,290.),boxes)
 def test_real_untitled_table_below_gap_remains_detected(self):
  boxes=three_line_tables(self.page())
  self.assertIn((60.,290.,520.,380.),boxes)
 def test_single_digit_data_row_is_valid_table_body(self):
  doc=pymupdf.open();self.addCleanup(doc.close);page=doc.new_page(width=600,height=800)
  for y in (150,170,260):page.draw_line((60,y),(520,y))
  page.insert_text((70,165),'Header',fontsize=10);page.insert_text((70,220),'7',fontsize=10)
  self.assertIn((60.,150.,520.,260.),three_line_tables(page))

if __name__=='__main__':unittest.main()
