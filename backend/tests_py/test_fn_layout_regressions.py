"""Real PDF regressions for split references, adjacent tables and grid diagrams."""
import io
import tempfile
import unittest
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from pdf_rules.engine import detect
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

class FnLayoutRegressions(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'paper.pdf'
    def save(self, pdf):
        pdf.save(self.path)
        pdf.close()
    def test_same_row_reference_fragments_keep_number_and_location(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        page.insert_text((60, 120), 'Results are shown in Figure', fontsize=12)
        end = page.get_text('dict')['blocks'][0]['lines'][0]['bbox'][2]
        page.insert_text((end + 10, 120), '7.8 for this experiment.', fontsize=10.5)
        self.save(pdf)
        findings = detect(self.path, [11])['rules']['11']['findings']
        self.assertEqual([f['token'] for f in findings], ['7.8'])
        self.assertGreater(findings[0]['location']['bounding_rect']['x1'], 60)
        self.assertIn('Figure', findings[0]['text_excerpt'])
    def test_reference_prefix_cannot_join_a_different_column_or_row(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        page.insert_text((60, 120), 'See Figure', fontsize=12)
        page.insert_text((360, 120), '7.8', fontsize=12)
        page.insert_text((128, 155), '6.9', fontsize=12)
        self.save(pdf)
        self.assertEqual(detect(self.path, [11])['rules']['11']['findings'], [])
    def test_centered_split_caption_between_two_tables_is_not_a_cell_reference(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        for y in (200, 220, 300, 320, 355, 375, 450):
            page.draw_line((80, y), (520, y))
        for y in (214, 270, 312, 369, 415):
            page.insert_text((100, y), 'Method', fontsize=10)
            page.insert_text((370, y), 'Value', fontsize=10)
        label = 'Table 7.4'; title = 'Configuration parameters'
        left_width = pymupdf.get_text_length(label, fontsize=12)
        right_width = pymupdf.get_text_length(title, fontname='tiro', fontsize=10.5)
        left = 300 - (left_width + 12 + right_width) / 2
        page.insert_text((left, 342), label, fontsize=12)
        page.insert_text((left + left_width + 12, 342), title, fontname='tiro', fontsize=10.5)
        self.save(pdf)
        findings = detect(self.path, [16])['rules']['16']['findings']
        self.assertEqual([f['token'] for f in findings], ['7.4'])
        self.assertIn('Configuration parameters', findings[0]['text_excerpt'])
    @staticmethod
    def grid_image(flow=True, broken=False):
        image = Image.new('RGB', (600, 500), 'white'); draw = ImageDraw.Draw(image)
        for x in (0, 200, 400, 599): draw.line((x, 0, x, 499), fill='black', width=2)
        for y in (0, 90, 250, 420, 499): draw.line((0, y, 599, y), fill='black', width=2)
        for x, y in ((100, 170), (300, 170), (100, 330), (300, 330)):
            draw.polygon([(x, y-28), (x+28, y), (x, y+28), (x-28, y)], fill='white', outline='black', width=2)
        if flow:
            for x in (100, 300):
                draw.line((x, 198, x, 300), fill='black', width=2)
                draw.line((x-7, 290, x, 300, x+7, 290), fill='black', width=2)
        if broken:
            for x in (100,300):
                draw.rectangle((x-3,225,x+3,238),fill='white')
        stream = io.BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()
    def layout_for_grid(self, flow, broken=False):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        page.insert_text((60, 90), 'Chapter 7 Experiments', fontsize=12)
        page.insert_image((90, 140, 510, 490), stream=self.grid_image(flow, broken))
        self.save(pdf)
        doc = extract_pdf(self.path)
        obj = LayoutObject('table', 1, (90, 140, 510, 490), 'Method data', 600, 800)
        return doc, prepare_caption_layout([obj], doc)
    def test_connected_diamond_flow_inside_grid_is_a_figure_even_without_caption(self):
        doc, objects = self.layout_for_grid(flow=True)
        rules = detect_caption_rules(objects, [13, 14], doc)
        self.assertEqual(len(rules['13']['findings']), 1)
        self.assertEqual(rules['14']['findings'], [])
    def test_diamond_symbols_in_grid_cells_do_not_turn_a_table_into_a_figure(self):
        doc, objects = self.layout_for_grid(flow=False)
        rules = detect_caption_rules(objects, [13, 14], doc)
        self.assertEqual(rules['13']['findings'], [])
        self.assertEqual(len(rules['14']['findings']), 1)
    def test_split_reference_highlight_is_on_the_missing_number(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        page.insert_text((60, 120), 'See Figure', fontsize=12)
        page.insert_text((130, 120), '7.8 has no target.', fontsize=10.5)
        self.save(pdf)
        finding = detect(self.path, [11])['rules']['11']['findings'][0]
        box = finding['location']['bounding_rect']
        self.assertAlmostEqual(box['x1'], 130, delta=.2)
        self.assertAlmostEqual(box['x2'], 144.6, delta=.2)

    def reference_in_table_pdf(self, cell_border=False):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        for y in (200, 220, 300):
            page.draw_line((80, y), (520, y))
        page.insert_text((100, 214), 'Reference', fontsize=10)
        page.insert_text((370, 214), 'Value', fontsize=10)
        page.insert_text((100, 260), 'See Table', fontsize=12)
        end = max(line['bbox'][2] for block in page.get_text('dict')['blocks']
                  if block['type'] == 0 for line in block['lines']
                  if ''.join(s['text'] for s in line['spans']) == 'See Table')
        page.insert_text((end + 10, 260), '7.4', fontsize=10.5)
        if cell_border:
            page.draw_line((end + 5, 200), (end + 5, 300))
        page.insert_text((190, 360), 'Table 7.4 Configuration parameters', fontsize=12)
        self.save(pdf)
    def test_split_reference_inside_one_table_cell_still_counts_as_citation(self):
        self.reference_in_table_pdf()
        self.assertEqual(detect(self.path, [16])['rules']['16']['findings'], [])
    def test_prefix_and_number_across_a_table_cell_border_are_not_a_citation(self):
        self.reference_in_table_pdf(cell_border=True)
        findings = detect(self.path, [16])['rules']['16']['findings']
        self.assertEqual([f['token'] for f in findings], ['7.4'])

    def test_adjacent_rectangular_cells_do_not_create_a_figure_reference(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        page.draw_rect((100, 200, 158, 300))
        page.draw_rect((158, 200, 220, 300))
        page.insert_text((120, 260), 'Figure', fontsize=10)
        page.insert_text((164, 260), '7.8', fontsize=10.5)
        self.save(pdf)
        self.assertEqual(detect(self.path, [11])['rules']['11']['findings'], [])

    def test_centered_numeric_table_row_is_not_an_external_caption(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600, height=800)
        for y in (200, 225, 300):
            page.draw_line((80, y), (520, y))
        page.insert_text((200, 220), 'Reference', fontsize=10)
        page.insert_text((330, 220), 'Value', fontsize=10)
        label = 'Table 2.1'; value = '0.95'
        lw = pymupdf.get_text_length(label, fontsize=12)
        vw = pymupdf.get_text_length(value, fontname='tiro', fontsize=10.5)
        left = 300-(lw+12+vw)/2
        page.insert_text((left, 260), label, fontsize=12)
        page.insert_text((left+lw+12, 260), value, fontname='tiro', fontsize=10.5)
        self.save(pdf)
        self.assertEqual(detect(self.path, [16])['rules']['16']['findings'], [])

    def test_numeric_stems_between_diamond_markers_are_not_flow_connectors(self):
        image = Image.new('RGB', (600,500), 'white'); draw = ImageDraw.Draw(image)
        for x in (0,200,400,599): draw.line((x,0,x,499),fill='black',width=2)
        for y in (0,150,330,499): draw.line((0,y,599,y),fill='black',width=2)
        for y in (70,250,430):
            draw.polygon(((300,y-28),(328,y),(300,y+28),(272,y)),fill='white',outline='black',width=2)
        font = ImageFont.truetype(io.BytesIO(pymupdf.Font('helv').buffer),24)
        for y in (*range(98,205,22),*range(278,385,22)):
            draw.text((293,y),'1',fill='black',font=font)
        stream = io.BytesIO(); image.save(stream,format='PNG')
        pdf = pymupdf.open(); page = pdf.new_page(width=600,height=800)
        page.insert_text((200,125),'Table 7.1 Numeric marker values',fontsize=12)
        page.insert_image((200,140,400,306.6667),stream=stream.getvalue())
        self.save(pdf)
        doc = extract_pdf(self.path)
        obj = LayoutObject('table',1,(200,140,400,306.6667),'Numeric data',600,800)
        objects = prepare_caption_layout([obj],doc)
        rules = detect_caption_rules(objects,[13,14],doc)
        self.assertEqual(rules['13']['findings'],[])
        self.assertEqual(rules['14']['findings'],[])

    def test_two_split_references_on_the_same_row_are_both_detected(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600,height=800)
        page.insert_text((60,120),'See Figure',fontsize=12)
        page.insert_text((130,120),'7.8 and Figure',fontsize=10.5)
        end = max(line['bbox'][2] for block in page.get_text('dict')['blocks']
                  if block['type'] == 0 for line in block['lines'])
        page.insert_text((end+10,120),'7.9',fontsize=12)
        self.save(pdf)
        findings = detect(self.path,[11])['rules']['11']['findings']
        self.assertEqual([f['token'] for f in findings],['7.8','7.9'])
        self.assertGreater(findings[1]['location']['bounding_rect']['x1'],end)

    def test_disconnected_line_segments_do_not_establish_flow_links(self):
        doc, objects = self.layout_for_grid(flow=True, broken=True)
        rules = detect_caption_rules(objects, [13,14], doc)
        self.assertEqual(rules['13']['findings'], [])
        self.assertEqual(len(rules['14']['findings']),1)

    def test_caption_between_tables_with_internal_rules_is_not_swallowed(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600,height=800)
        for y in (180,200,220,240,260,280,320,340,360,380,400):
            page.draw_line((80,y),(520,y))
        for y in (194,214,234,254,274,334,354,374,394):
            page.insert_text((100,y),'Method',fontsize=10)
            page.insert_text((370,y),'Value',fontsize=10)
        label = 'Table 8.2'; title = 'Execution configuration'
        lw = pymupdf.get_text_length(label,fontsize=12)
        tw = pymupdf.get_text_length(title,fontname='tiro',fontsize=10.5)
        left = 300-(lw+12+tw)/2
        page.insert_text((left,306),label,fontsize=12)
        page.insert_text((left+lw+12,306),title,fontname='tiro',fontsize=10.5)
        self.save(pdf)
        findings = detect(self.path,[16])['rules']['16']['findings']
        self.assertEqual([f['token'] for f in findings],['8.2'])

    def test_filled_thin_rectangle_divider_prevents_cross_cell_reference(self):
        pdf = pymupdf.open(); page = pdf.new_page(width=600,height=800)
        for y in (200,220,300): page.draw_line((100,y),(520,y))
        page.insert_text((120,214),'Reference',fontsize=10)
        page.insert_text((370,214),'Value',fontsize=10)
        page.draw_rect((157,200,159,300),fill=(0,0,0),color=None)
        page.insert_text((120,260),'Figure',fontsize=10)
        page.insert_text((164,260),'7.8',fontsize=10.5)
        self.save(pdf)
        self.assertEqual(detect(self.path,[11])['rules']['11']['findings'],[])
