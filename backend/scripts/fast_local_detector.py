"""Reuse the existing PDF frontend and local detector; no model client is created."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import build_paper
from paper_compiler.local_checks import RULES, detect_ir
from five_rule_detector import RULES as OLD_RULES, detect_pdf


def native_coverage(ir):
    pages = ir['layout']['pages']
    complete = all(page.get('lines') or not page.get('images') for page in pages)
    for page in pages:
        area = page['width'] * page['height']
        large_image = any((box[2]-box[0])*(box[3]-box[1]) > area*.5 for box in page.get('images', []))
        interior = sum(len(line['text'].strip()) for line in page.get('lines', []) if page['height']*.15 < line['bbox'][1] < page['height']*.9)
        if large_image and interior < 80:
            complete = False
    ir['coverage']['pages'] = ({'status': 'complete', 'protocol': 'native-text-and-blank-pages/1.1', 'evidence_ids': [ir['root_id']]} if complete else
                              {'status': 'partial', 'reason': 'image content is not read; no OCR or API is used'})
    return ir


def load_ir(pdf):
    return native_coverage(build_paper(pdf, include_citations=False))


def run(pdf, selected):
    started = time.perf_counter()
    old = [r for r in selected if r in OLD_RULES]
    new = [r for r in selected if r in RULES]
    result = detect_pdf(pdf, old) if old else {'pdf': str(pdf), 'rules': {}}
    if new:
        ir = load_ir(pdf)
        result['rules'].update(detect_ir(ir, new))
        result['pages'] = len(ir['layout']['pages'])
        result['paper_model_version'] = ir['model_version']
        result['paper_ir_version'] = ir['schema_version']
    result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 1)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--rule', type=int, action='append', choices=(*OLD_RULES, *RULES))
    args = parser.parse_args()
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    print(json.dumps(run(args.pdf, args.rule or [18, 22, 24, 28, 31, 34, 35, 36]), ensure_ascii=True))
