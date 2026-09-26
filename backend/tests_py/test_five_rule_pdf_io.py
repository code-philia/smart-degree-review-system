import tempfile
import unittest
from pathlib import Path
import sys

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import detect_pdf


class PdfInputTests(unittest.TestCase):
    def test_unrelated_generated_pdf_can_be_checked_with_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'external-paper.pdf'
            pdf = pymupdf.open()
            page = pdf.new_page()
            page.insert_text((70, 90), 'Introduction', fontsize=16)
            page.insert_text((70, 140), 'Prior study [1] is compared with unknown study [99].', fontsize=11)
            page = pdf.new_page()
            page.insert_text((70, 90), 'References', fontsize=16)
            page.insert_text((70, 140), '[1] Known work, 2025.', fontsize=11)
            page.insert_text((70, 170), '[2] Uncited work, 2024.', fontsize=11)
            pdf.save(path)
            pdf.close()
            result = detect_pdf(path, [22, 24])['rules']
            self.assertEqual([f['token'] for f in result['22']['findings']], ['99'])
            self.assertEqual([f['token'] for f in result['24']['findings']], ['2'])
            location = result['22']['findings'][0]['location']
            self.assertEqual(location['page_number'], 1)
            self.assertGreater(location['bounding_rect']['x2'], location['bounding_rect']['x1'])


if __name__ == '__main__':
    unittest.main()
