import os
from pathlib import Path

from .caption_rules import detect_caption_rules
from .index import build_index
from .local_rules import detect_rules
from .mineru_api import MinerUError, parse_layout
from .pdf_extract import extract_pdf


LOCAL = {11, 15, 16, 29}
CLOUD = {13, 14}


def detect(pdf_path: str | Path, selected_rule_numbers, *, token=None, http_client=None) -> dict:
    selected = set(selected_rule_numbers)
    document = extract_pdf(pdf_path)
    results = {}
    if selected & LOCAL:
        index = build_index(document)
        results.update(detect_rules(index, selected & LOCAL))
    if selected & CLOUD:
        try:
            objects = parse_layout(pdf_path, token if token is not None else os.environ.get("MINERU_API_TOKEN"),
                                   http_client)
            results.update(detect_caption_rules(objects, selected & CLOUD))
        except MinerUError as exc:
            for number in selected & CLOUD:
                results[str(number)] = {"status": "unsupported", "reason": str(exc), "findings": []}
    return {"pages": len(document.pages), "rules": results}
