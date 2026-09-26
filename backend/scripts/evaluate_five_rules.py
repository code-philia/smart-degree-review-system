"""Evaluate local five-rule PDF detectors against mother/mutant pairs.

Mutation plans are read here only for scoring. They are never passed into the
detector. Reports are local and resumable; no thesis content leaves the host.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from five_rule_detector import RULES, detect_pdf


def _clean(text: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff]', '', str(text)).casefold()


def expected_sites(rule: int, mutation_plan: dict) -> list[dict]:
    plan = mutation_plan.get('plan', mutation_plan)
    if rule == 6:
        changes = plan.get('replacements', [])
        return [{'page': int(plan.get('abstract_page', changes[0]['page'])),
                 'text': changes[0]['new_text']}] if changes else []
    if rule in (18, 22):
        marker = plan['new_marker'].replace('．', '.').replace('－', '-')
        allowed = r'[^\d.\-]' if rule == 18 else r'\D'
        return [{'page': int(plan['page']), 'token': re.sub(allowed, '', marker)}]
    if rule == 24:
        return [{'page': int(plan['target_page']), 'token': re.sub(r'\D', '', plan['new_marker'])}]
    if rule == 28:
        return [{'page': int(entry['page']), 'token': str(entry['new_text']),
                 'top': float(entry['top'])} for entry in plan['entries']]
    raise ValueError(f'未知规则 {rule}')


def _matches(rule: int, site: dict, finding: dict) -> bool:
    if int(finding.get('page', 0)) != site['page']:
        return False
    if rule == 6:
        return _clean(site['text'])[:22] in _clean(finding.get('text_excerpt', ''))
    if str(finding.get('token', '')) != site['token']:
        return False
    if rule == 28:
        bbox = finding.get('bbox', [])
        return bool(bbox and abs(float(bbox[1]) - site['top']) <= 12)
    return True


def _same_finding(left: dict, right: dict) -> bool:
    if left.get('page') != right.get('page') or str(left.get('token', '')) != str(right.get('token', '')):
        return False
    left_box, right_box = left.get('bbox', []), right.get('bbox', [])
    if len(left_box) >= 2 and len(right_box) >= 2:
        return abs(left_box[1] - right_box[1]) <= 12 and abs(left_box[0] - right_box[0]) <= 50
    return _clean(left.get('text_excerpt', '')) == _clean(right.get('text_excerpt', ''))


def _unique_matches(rule: int, sites: list[dict], findings: list[dict]) -> int:
    unused = set(range(len(findings)))
    matches = 0
    for site in sites:
        for index in sorted(unused):
            if _matches(rule, site, findings[index]):
                unused.remove(index)
                matches += 1
                break
    return matches


def score_pair(rule: int, mutation_plan: dict, mother: dict, mutant: dict) -> dict:
    sites = expected_sites(rule, mutation_plan)
    baseline = mother.get('findings', []) if mother.get('status') == 'completed' else []
    found = mutant.get('findings', []) if mutant.get('status') == 'completed' else []
    unmatched_baseline = list(baseline)
    new_findings = []
    for finding in found:
        match_index = next((i for i, prior in enumerate(unmatched_baseline)
                            if _same_finding(prior, finding)), None)
        if match_index is None:
            new_findings.append(finding)
        else:
            unmatched_baseline.pop(match_index)
    detected = _unique_matches(rule, sites, found)
    matched_new = _unique_matches(rule, sites, new_findings)
    return {'expected_sites': len(sites), 'detected_sites': detected,
            'mutation_detected': detected > 0, 'baseline_findings': len(baseline),
            'mutant_findings': len(found), 'new_findings': len(new_findings),
            'matched_new_findings': matched_new,
            'other_new_findings': len(new_findings) - matched_new,
            'unsupported': mutant.get('status') != 'completed',
            'mother_unsupported': mother.get('status') != 'completed',
            'mutant_reason': mutant.get('reason', ''), 'mother_reason': mother.get('reason', '')}


def _records(manifest: dict, rules: list[int], limit: int = 0) -> list[dict]:
    records = []
    for rule in rules:
        files = manifest['rules'][str(rule)]['files']
        for entry in files[:limit or None]:
            records.append({'rule': rule, **entry})
    return records


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def preflight(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    root = manifest_path.parents[2]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    counts = {str(rule): len(manifest['rules'][str(rule)]['files']) for rule in RULES}
    missing = []
    for record in _records(manifest, list(RULES)):
        for field in ('pdf', 'mother', 'mutation_plan_json'):
            if not _path(root, record[field]).is_file():
                missing.append({'rule': record['rule'], 'number': record['number'], 'field': field})
    return {'manifest': str(manifest_path), 'workspace_root': str(root),
            'counts': counts, 'missing': missing,
            'ready_500': sum(counts.values()) == 500 and all(v == 100 for v in counts.values()) and not missing}


def _summary(records: list[dict]) -> dict:
    output = {}
    for rule in RULES:
        subset = [r for r in records if r['rule'] == rule]
        if not subset:
            continue
        totals = {key: sum(int(r[key]) for r in subset) for key in
                  ('expected_sites', 'detected_sites', 'baseline_findings', 'mutant_findings',
                   'new_findings', 'matched_new_findings', 'other_new_findings')}
        totals.update({'pairs': len(subset),
                       'mutants_detected': sum(bool(r['mutation_detected']) for r in subset),
                       'unsupported_mutants': sum(bool(r['unsupported']) for r in subset),
                       'unsupported_mothers': sum(bool(r['mother_unsupported']) for r in subset)})
        totals['site_recall'] = totals['detected_sites'] / totals['expected_sites'] if totals['expected_sites'] else None
        totals['mutant_recall'] = totals['mutants_detected'] / totals['pairs']
        totals['paired_incremental_precision_proxy'] = (totals['matched_new_findings'] / totals['new_findings']
                                                         if totals['new_findings'] else None)
        output[str(rule)] = totals
    return output


def run(manifest_path: Path, output_path: Path, rules: list[int], limit: int = 0) -> dict:
    check = preflight(manifest_path)
    if check['missing']:
        raise RuntimeError(f"变异清单缺少 {len(check['missing'])} 个输入文件")
    root = Path(check['workspace_root'])
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        report = json.loads(output_path.read_text(encoding='utf-8'))
        if report.get('manifest') != str(manifest_path.resolve()):
            raise RuntimeError('输出文件属于其他 manifest，请换用新的 --output 路径')
    else:
        report = {'manifest': str(manifest_path.resolve()), 'records': [], 'summary': {}}
    done = {(int(r['rule']), int(r['number'])) for r in report['records']}
    mother_cache = {}
    for entry in _records(manifest, rules, limit):
        key = (entry['rule'], entry['number'])
        if key in done:
            continue
        start = time.monotonic()
        mother_path = _path(root, entry['mother'])
        mutant_path = _path(root, entry['pdf'])
        if str(mother_path) not in mother_cache:
            mother_cache[str(mother_path)] = detect_pdf(mother_path, RULES)['rules']
        mother = mother_cache[str(mother_path)][str(entry['rule'])]
        mutant = detect_pdf(mutant_path, [entry['rule']])['rules'][str(entry['rule'])]
        plan = json.loads(_path(root, entry['mutation_plan_json']).read_text(encoding='utf-8'))
        scored = score_pair(entry['rule'], plan, mother, mutant)
        report['records'].append({'rule': entry['rule'], 'number': entry['number'],
                                  'mother': entry['mother'], 'mutant': entry['pdf'],
                                  'changed_pages': entry['changed_pages'],
                                  'elapsed_seconds': round(time.monotonic() - start, 3),
                                  **scored})
        report['summary'] = _summary(report['records'])
        temp = output_path.with_suffix(output_path.suffix + '.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(output_path)
        print(f"rule={entry['rule']} mutant={entry['number']} detected={scored['detected_sites']}/{scored['expected_sites']} unsupported={scored['unsupported']}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='本地 500 份 PDF 变异检测评测')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--rule', action='append', type=int, choices=RULES)
    parser.add_argument('--limit', type=int, default=0, help='每条规则最多试跑多少份；0 表示全部')
    parser.add_argument('--preflight', action='store_true', help='仅检查 500 份输入是否齐全')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit 必须大于或等于 0')
    if args.preflight:
        check = preflight(args.manifest)
        print(json.dumps(check, ensure_ascii=False, indent=2))
        raise SystemExit(0 if check['ready_500'] else 1)
    if not args.output:
        parser.error('运行评测时必须指定 --output')
    report = run(args.manifest, args.output, args.rule or list(RULES), args.limit)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
