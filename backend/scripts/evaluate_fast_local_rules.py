"""Archive regression and reproducible Paper IR mutants; no external services."""
import argparse
import copy
import gzip
import itertools
import json
from pathlib import Path
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fast_local_detector import load_ir, native_coverage
from paper_compiler.local_checks import detect_ir, core_parts, compact, rows, prose_nodes, _TYPE, _PUNCT, _INTRO, _CONCLUSION, _CHAPTER
from paper_compiler.contracts import validate_ir


def write_ir(path, ir):
    with gzip.open(path, 'wt', encoding='utf-8', compresslevel=1) as out:
        json.dump(ir, out, ensure_ascii=True, separators=(',', ':'))


def scan(item):
    index, pdf, output = item
    started = time.perf_counter()
    try:
        ir = load_ir(Path(pdf)); found = detect_ir(ir)
        complete = ir['coverage']['pages']['status'] == 'complete'
        core_clean = complete and all(core_parts(ir).values())
        cached = None
        if True:
            cached = str(Path(output) / 'mothers' / f'{index:03}.json.gz')
            write_ir(cached, ir)
        return {'index': index, 'pdf': pdf, 'elapsed_ms': round((time.perf_counter()-started)*1000, 1),
                'native_complete': complete, 'core_clean': core_clean, 'cache': cached, 'rules': found}
    except Exception as error:
        return {'index': index, 'pdf': pdf, 'error': type(error).__name__+': '+str(error)}


def rescan_cached(item):
    record, output = item
    if record.get('error') or not record.get('cache'):
        return scan((record['index'],record['pdf'],output))
    with gzip.open(record['cache'],'rt',encoding='utf-8') as f:ir=json.load(f)
    for page in ir['layout']['pages']:
        for line in page.get('lines',[]):line.pop('chars',None)
    ir=native_coverage(ir)
    found=detect_ir(ir)
    cache=record['cache']
    return {**record,'cache':cache,'native_complete':ir['coverage']['pages']['status']=='complete',
            'core_clean':ir['coverage']['pages']['status']=='complete' and all(core_parts(ir).values()),'rules':found}


def drop_subtrees(ir, roots):
    by_id = {node['id']: node for node in ir['nodes']}
    removed = set(); pending = list(roots)
    while pending:
        nid = pending.pop()
        if nid not in removed:
            removed.add(nid); pending.extend(by_id[nid]['children'])
    ir['nodes'] = [node for node in ir['nodes'] if node['id'] not in removed]
    for node in ir['nodes']:
        node['children'] = [nid for nid in node['children'] if nid not in removed]


def core_roots(ir):
    options = {}
    for kind in ['Abstract', 'ToC', 'Bibliography']:
        roots = [node['id'] for node in ir['nodes'] if node['kind'] == kind]
        if roots: options[kind] = roots
    # A split Chinese abstract heading can be ordinary IR text even when the English abstract is typed. Remove both source-page regions.
    abstract_pages={page for page,_,text,_ in rows(ir) if compact(text) in {'摘要','中文摘要','abstract','英文摘要'}}
    abstract_nodes=[node['id'] for node in ir['nodes'] if any(span.get('page_index') in abstract_pages for span in node['provenance'])]
    if abstract_nodes:options['Abstract']=list(dict.fromkeys(options.get('Abstract',[])+abstract_nodes))
    by_id = {node['id']: node for node in ir['nodes']}
    for name, pattern in [('Introduction', _INTRO), ('Conclusion', _CONCLUSION)]:
        roots = [node['id'] for node in ir['nodes'] if node['kind'] == 'Section' and
                 any(by_id[child]['kind'] == 'Heading' and pattern.fullmatch(_CHAPTER.sub('', compact(by_id[child]['text'])))
                     for child in node['children'])]
        if roots: options[name] = roots
    visual=rows(ir)
    def on_pages(pages):
        return [node['id'] for node in ir['nodes'] if any(span.get('page_index') in pages for span in node['provenance'])]
    for name,pattern in [('Originality',r'原创性声明|独创性声明|原创声明|学术诚信声明'),('Authorization',r'(?:使用|版权)授权|版权使用')]:
        pages={page for page,_,text,_ in visual if re.search(pattern,compact(text))}
        if pages:options[name]=on_pages(pages)
    keyword_nodes=[n['id'] for n in ir['nodes'] if re.search(r'(?:^|\n)\s*(?:关键词|关键字|key\s*words?)\s*[:：]',n['text'] or '',re.I)]
    if keyword_nodes:options['Keywords']=keyword_nodes
    front_end=min((page for page,_,text,_ in visual if compact(text) in {'摘要','abstract','目录','contents'}),default=6)
    title_pages={page for page,_,text,_ in visual if page<front_end and re.match(r'^(?:作者|姓名|学号|导师|指导教师|学科|专业|学院|申请学位|student|supervisor|department)',compact(text))}
    if title_pages:
        declaration_start=min((page for page,_,text,_ in visual if re.search(r'原创性声明|独创性声明|使用授权|版权使用',compact(text))),default=front_end)
        options['TitlePage']=on_pages(set(range(min(front_end,declaration_start))))
    intro_pages={span['page_index'] for nid in options.get('Introduction',[]) for child in by_id[nid]['children'] for span in by_id[child]['provenance'] if span.get('kind')=='source'}
    if intro_pages:
        main=[n['id'] for n in ir['nodes'] if n['kind']=='Section' and n['attrs'].get('level',1)==1 and n['id'] not in options.get('Introduction',[])+options.get('Conclusion',[]) and
              any(span.get('page_index',-1)>=min(intro_pages) for child in n['children'] for span in by_id[child]['provenance'])]
        if main:options['MainBody']=main
    return options


def candidates(ir, rule):
    if rule == 34:
        options = core_roots(ir)
        for count in [1, 2]:
            for keys in itertools.combinations(options, count):
                yield ('remove_'+'_'.join(keys), [nid for key in keys for nid in options[key]], None, None)
    elif rule == 31:
        for node in ir['nodes']:
            if node['kind'] != 'BibliographyEntry': continue
            matches = list(_TYPE.finditer(node['text']))
            if len(matches) != 1: continue
            match = matches[0]
            for recipe, replacement in [('missing_marker', ''), ('invalid_marker', '[XYZ]'), ('unclosed_marker', match.group()[:-1])]:
                yield (recipe, [node['id']], [match.start(), match.end()], replacement)
    else:
        for node in prose_nodes(ir):
            if re.search(r'https?://|www\.|[`=<>]|\b(?:print|def|return|import|if|while)\s*\(', node['text']): continue
            for match in re.finditer(r'[\u4e00-\u9fff]([，；：！？])(?=[\u4e00-\u9fff])', node['text']):
                if re.search(r'(?:字符|符号|终止符|分隔符|标点|运算符)\s*$', node['text'][:match.start(1)]): continue
                yield ('halfwidth_punctuation', [node['id']], [match.start(1), match.end(1)],
                       dict(zip('，；：！？', ',;:!?'))[match.group(1)])


def mutate(ir, case_id, rule, change):
    mutant = {**ir, 'nodes': [dict(node) for node in ir['nodes']]}; recipe, targets, span, replacement = change
    mutant['revision'] = case_id
    if rule == 34:
        drop_subtrees(mutant, targets)
    else:
        node = next(node for node in mutant['nodes'] if node['id'] == targets[0])
        node['text'] = node['text'][:span[0]] + replacement + node['text'][span[1]:]
        node['provenance'] = [{'kind': 'synthetic', 'operation_id': case_id,
                               'ancestor_provenance': node['provenance']}]
    validate_ir(mutant)
    return mutant


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--reuse', type=Path)
    args=parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    for folder in ['mothers', 'mutants']:(args.output/folder).mkdir(exist_ok=True)
    pdfs=sorted(args.archive_root.rglob('*.pdf')); records=[]; start=time.perf_counter()
    if args.reuse:
        old_records=json.loads((args.reuse/'archive-results.json').read_text())
        with ProcessPoolExecutor(args.workers) as pool:
            records=list(pool.map(rescan_cached, [(record,str(args.output)) for record in old_records]))
        print('rechecked cached Paper IR',len(records),flush=True)
    else:
        with ProcessPoolExecutor(args.workers) as pool:
            for record in pool.map(scan, [(i,str(p),str(args.output)) for i,p in enumerate(pdfs)]):
                records.append(record)
                if len(records)%40==0: print('scanned',len(records), '/',len(pdfs),flush=True)
    (args.output/'archive-results.json').write_text(json.dumps(records,ensure_ascii=True,indent=2))
    summary={}; manifest=[]
    for rule in [31,34,35]:
        count=tp=fp=0; mothers=set()
        for record in records:
            if not record.get('cache') or record.get('error') or record['rules'][str(rule)]['findings']: continue
            if rule==34 and not record['core_clean']: continue
            with gzip.open(record['cache'],'rt',encoding='utf-8') as f:ir=json.load(f)
            per_mother=0
            for change in candidates(ir,rule):
                if count>=100 or per_mother>=(20 if rule==34 else 10): break
                per_mother+=1
                case_id=f'local-{rule}-{count+1:03}'
                mutant=mutate(ir,case_id,rule,change)
                result=detect_ir(mutant,[rule])[str(rule)]
                if rule == 34:
                    labels={'Abstract':'摘要','ToC':'目录','Bibliography':'参考文献','Introduction':'引言','Conclusion':'结论','Originality':'原创性声明','Authorization':'使用授权说明','Keywords':'关键词','TitlePage':'题名页','MainBody':'主体'}
                    required=[labels[name] for name in change[0].removeprefix('remove_').split('_')]
                    detected=set(required).issubset({f['token'] for f in result['findings']})
                else:
                    detected=any(f['node_id'] in change[1] for f in result['findings'])
                tp+=int(detected);count+=1
                parent_result=detect_ir(ir,[rule])[str(rule)];fp+=int(bool(parent_result['findings']))
                target=args.output/'mutants'/f'{case_id}.json.gz';write_ir(target,mutant)
                mothers.add(record['pdf'])
                manifest.append(dict(case_id=case_id,rule=rule,mother_pdf=record['pdf'],mother_ir=record['cache'],mutant_ir=str(target),
                                     recipe=change[0],target_nodes=change[1],source_range=change[2],replacement=change[3],
                                     detected=detected,findings=result['findings']))
            if count>=100: break
        summary[str(rule)]=dict(mutants=count,mother_pdfs=len(mothers),TP=tp,FN=count-tp,FP=fp,
                                precision=tp/(tp+fp) if tp+fp else None,recall=tp/count if count else None)
        print('mutation',rule,summary[str(rule)],flush=True)
    (args.output/'mutation-cases.json').write_text(json.dumps(manifest,ensure_ascii=True,indent=2))
    (args.output/'summary.json').write_text(json.dumps(dict(rules=summary,archive_pdfs=len(records),errors=sum('error' in r for r in records),
        elapsed_seconds=round(time.perf_counter()-start,1),method='100 IR mutants per rule with corresponding mothers; mothers selected without target-rule findings; no train/validation split; native-text only'),ensure_ascii=True,indent=2))


if __name__=='__main__':main()
