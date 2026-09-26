import json
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import detect_pdf, extract_lines


class PdfInputTests(unittest.TestCase):
    def test_text_extraction_does_not_decode_image_payloads(self):
        class ImageHeavyPage:
            rect = SimpleNamespace(width=600, height=800)

            def get_text(self, kind, *, sort, flags=None):
                if flags is None or flags & pymupdf.TEXT_PRESERVE_IMAGES:
                    raise MemoryError('image payload exceeds the memory budget')
                return {
                    'blocks': [{
                        'type': 0,
                        'lines': [{
                            'bbox': (70, 80, 180, 92),
                            'spans': [{'text': 'Visible text', 'size': 12}],
                        }],
                    }],
                }

        with patch.object(pymupdf, 'open', return_value=nullcontext([ImageHeavyPage()])):
            lines, pages = extract_lines(Path('image-heavy.pdf'))

        self.assertEqual(pages, 1)
        self.assertEqual([(line.text, line.page, line.bbox) for line in lines],
                         [('Visible text', 1, (70, 80, 180, 92))])

    def test_cli_emits_json_when_mupdf_reports_a_malformed_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'malformed-stream.pdf'
            pdf = pymupdf.open()
            pdf.new_page().insert_text((70, 90), 'Visible text')
            data = pdf.tobytes(deflate=False)
            pdf.close()
            self.assertIn(b'BT\n', data)
            path.write_bytes(data.replace(b'BT\n', b'XX\n', 1))

            script = Path(__file__).resolve().parents[1] / 'scripts' / 'five_rule_detector.py'
            process = subprocess.run(
                [sys.executable, str(script), '--pdf', str(path), '--rule', '18'],
                capture_output=True, text=True, check=True, timeout=15,
            )
            result = json.loads(process.stdout)
            self.assertEqual(result['rules']['18']['status'], 'completed')
            self.assertIn('syntax error', process.stderr)

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
