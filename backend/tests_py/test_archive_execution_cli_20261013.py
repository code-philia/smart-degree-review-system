"""The detector CLI must keep recoverable PDF diagnostics out of its JSON pipe."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf


class ArchiveExecutionCliTests(unittest.TestCase):
    def test_recoverable_malformed_graphic_operator_keeps_json_stdout(self):
        # Losing the explicit PyMuPDF diagnostic destination makes this fail:
        # MuPDF recovers the malformed operator but prefixes stdout with an error.
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = Path(folder) / "recoverable-operator.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=600, height=800)
                page.insert_text((60, 90), "Methods and results of the experiment.")
                page.insert_text((60, 120), "We compare the measured values across all samples.")
                xref = page.get_contents()[0]
                pdf.update_stream(xref, b"qqq\n" + pdf.xref_stream(xref))
                pdf.save(pdf_path)
            script = Path(__file__).resolve().parents[1] / "scripts/six_rule_detector.py"
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            environment.pop("MINERU_API_TOKEN", None)
            run = subprocess.run(
                [sys.executable, str(script), "--pdf", str(pdf_path), "--rule", "11"],
                capture_output=True, text=True, env=environment, timeout=30,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.lstrip().startswith("{"), run.stdout[:300])
        self.assertEqual(json.loads(run.stdout)["rules"]["11"]["status"], "completed")
        self.assertIn("unknown keyword: 'qqq'", run.stderr)


if __name__ == "__main__":
    unittest.main()
