"""Local PDF metrics: hand-counted bilingual fixtures, with no network or OCR."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import fitz
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pdf_document_metrics.py"


def load_metrics():
    spec = importlib.util.spec_from_file_location("pdf_document_metrics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("text, expected", [
    ("中文论文 English words.", 6),
    ("中English文 2026, don't!", 5),
    ("inter-\nnational co-\r\noperation 中文", 4),
    ("，。！？ -- ___ …", 0),
    ("𠀀漢字 café ﬁndings", 5),
])
def test_counting_characters_and_words(text, expected):
    assert load_metrics().count_text_words(text) == expected


def test_cli_counts_whole_pdf_including_headers_and_references(tmp_path):
    pdf = tmp_path / "whole.pdf"
    with fitz.open() as document:
        first = document.new_page()
        first.insert_text((50, 50), "Header one\ninter-\nnational paper")
        first.insert_text((50, 150), "中文论文", fontname="china-s")
        document.new_page().insert_text((50, 50), "References\nSmith 2026")
        document.save(pdf)
    completed = subprocess.run([sys.executable, str(SCRIPT), str(pdf)], capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "page_count": 2, "word_count": 11, "text_available": True,
        "counting_method": "cjk_characters_and_words",
    }


def test_image_only_pdf_keeps_pages_without_inventing_a_zero_word_count(tmp_path):
    pdf = tmp_path / "scan.pdf"
    with fitz.open() as document:
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10))
        pixmap.clear_with(255)
        document.new_page().insert_image(fitz.Rect(30, 30, 130, 130), pixmap=pixmap)
        document.new_page()
        document.save(pdf)
    assert load_metrics().extract_pdf_metrics(pdf) == {
        "page_count": 2, "word_count": None, "text_available": False,
        "counting_method": "cjk_characters_and_words",
    }


def test_invalid_pdf_fails_without_emitting_paths_or_tracebacks(tmp_path):
    pdf = tmp_path / "private-file-name.pdf"
    pdf.write_bytes(b"not a PDF")
    completed = subprocess.run([sys.executable, str(SCRIPT), str(pdf)], capture_output=True, text=True, timeout=10)
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert str(pdf) not in completed.stderr
    assert "Traceback" not in completed.stderr
