"""Small synthetic numeric review acceptance fixture; never reads real papers."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pymupdf as fitz
import run_bilingual_semantic_lint as runtime
from numeric_consistency import source_model, structure_context
from paper_model_bilingual_rules import extract_bilingual_facts


def make_pdf(target, value='92.5', experiments=True):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 80), 'Abstract', fontsize=16)
    page.insert_text((60, 120), 'We propose a dynamic-weight Fusion model for Dataset A.', fontsize=12)
    page.insert_text((60, 145), 'The proposed Fusion model achieves 92.5% accuracy on Dataset A.', fontsize=12)
    page.insert_text((60, 180), 'Keywords: Fusion; Accuracy; Dataset A', fontsize=12)
    page.insert_text((60, 250), 'Contents', fontsize=16)
    page.insert_text((60, 285), 'Fusion model .................................................... 2', fontsize=12)
    page.insert_text((60, 310), 'Experiments ...................................................... 2', fontsize=12)
    page = doc.new_page()
    page.insert_text((60, 80), 'Chapter 3 Fusion model', fontsize=16)
    page.insert_text((60, 120), 'We propose a dynamic-weight Fusion model for Dataset A.', fontsize=12)
    if experiments:
        page.insert_text((60, 180), '3.1 Experiments', fontsize=16)
        page.insert_text((60, 220), 'Accuracy was measured on the Dataset A test set.', fontsize=12)
        page.insert_text((60, 250), 'The proposed Fusion model achieves ' + value + '% accuracy on Dataset A.', fontsize=12)
        page.insert_text((60, 290), 'Table 3-1 Accuracy on Dataset A', fontsize=12)
        page.insert_text((60, 320), 'Method           Dataset         Accuracy', fontsize=12)
        page.insert_text((60, 345), 'Fusion           A               ' + value + '%', fontsize=12)
    else:
        page.insert_text((60, 180), '3.1 Method implementation', fontsize=16)
        page.insert_text((60, 220), 'The architecture combines two dynamic feature streams.', fontsize=12)
    doc.save(target)
    doc.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['consistent', 'conflict', 'missing-experiments'], default='conflict')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pdf = args.output / (args.case + '.pdf')
    make_pdf(pdf, '89.3' if args.case == 'conflict' else '92.5', args.case != 'missing-experiments')
    ir = runtime.build_paper(pdf, include_citations=False)
    facts = extract_bilingual_facts(ir)
    model = source_model(ir)
    context = structure_context(facts, model)
    print(json.dumps({'case': args.case, 'abstract_present': bool(context['abstract']), 'toc_count': len(context['toc']),
                      'sections': [{'id': s['section_id'], 'title': s['title'], 'parent': s['parent_id']} for s in model['sections'].values()],
                      'source_has_experiment_value': any('89.3%' in b['text'] for b in model['blocks'])}, ensure_ascii=False), flush=True)
    if not args.live:
        return
    os.environ['PAPER_NUMERIC_RUNS_DIR'] = str(args.output / 'runs')
    started = time.monotonic()
    result = runtime.run_numeric_consistency_rule(ir, run_id='synthetic-' + args.case)
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'elapsed_seconds': time.monotonic()-started, 'execution_status': result['execution_status'],
                      'outcome': result['outcome'], 'message': result['message'], 'usage': result['model_usage'],
                      'failure': result['params'].get('failure'), 'trace': result['params'].get('trace'),
                      'preconditions': result['params'].get('preconditions'),
                      'results': [{'id': r['declaration_id'], 'status': r['status'], 'reason': r['reason'], 'evidence': r.get('evidence_quote')} for r in result['params'].get('numeric_results', [])]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
