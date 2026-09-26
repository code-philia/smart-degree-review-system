from pathlib import Path

from .index import build_index
from .local_rules import detect_rules
from .pdf_extract import extract_pdf


def detect(pdf_path: str | Path, selected_rule_numbers) -> dict:
    document = extract_pdf(pdf_path)
    index = build_index(document)
    return {"pages": len(document.pages), "rules": detect_rules(index, selected_rule_numbers)}

