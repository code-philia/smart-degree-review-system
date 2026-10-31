"""Extract whole-document metrics locally with PyMuPDF; never OCR or call a model."""
import json
import re
import sys
import unicodedata

import pymupdf as fitz

COUNTING_METHOD = "cjk_characters_and_words"
HAN = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ebef\U00030000-\U000323af]")
WORDS = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
LINE_BREAK_HYPHEN = re.compile(r"(?<=[A-Za-z])[-\u00ad][ \t]*\r?\n[ \t]*(?=[A-Za-z])")


def count_text_words(text):
    """Count each Han character and each remaining alphanumeric word once.

    Punctuation and underscores do not count. Apostrophes inside words stay
    together; ordinary hyphens separate words, except Latin line-wrap hyphens.
    Numbers count as words, including page numbers and reference entries.
    """
    text = unicodedata.normalize("NFKC", text)
    text = LINE_BREAK_HYPHEN.sub("", text).replace("\u00ad", "")
    chinese_count = len(HAN.findall(text))
    return chinese_count + len(WORDS.findall(HAN.sub(" ", text)))


def extract_pdf_metrics(pdf_path):
    # Per-page counting avoids loading an entire thesis into a single string.
    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("password-protected PDF")
        page_count = document.page_count
        word_count = sum(count_text_words(page.get_text("text", sort=True)) for page in document)
    return {
        "page_count": page_count,
        "word_count": word_count if word_count else None,
        "text_available": bool(word_count),
        "counting_method": COUNTING_METHOD,
    }


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("A PDF file is required.\n")
        return 2
    try:
        payload = extract_pdf_metrics(sys.argv[1])
    except Exception:
        # A private upload path and extracted text must never enter HTTP errors.
        sys.stderr.write("Unable to read PDF document metrics.\n")
        return 1
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
