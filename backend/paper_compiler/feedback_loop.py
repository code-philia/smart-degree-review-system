"""Counterexample-guided refinement with sealed labels and disjoint evaluation roles."""
import copy
import hashlib
import json
from pathlib import Path

from .budget import BudgetExceeded
from .contracts import validate_ir,ir_hash
from .programs import digest,load_program
from .storage import write_json_atomic
from .synthesis import synthesize_program

class FeedbackError(ValueError):
    pass

def load(path):
    return json.loads(Path(path).read_text())

def _fingerprint(manifest_path,manifest):
    paths={str(Path(manifest_path).resolve())}
    for case in manifest['cases']:
        paths.update(str(Path(case[k]).resolve()) for k in ['ir_path','original_ir_path','oracle_path'])
    return digest({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)})

def _actual(report,node_id,rule_id=None,node_ids=None):
    if report.get('_execution_error'):
        return 'ERROR',[{'node_id':node_id,'rule_id':rule_id,'status':'ERROR','message':'execution failed','error_type':report['_execution_error']}]
    targets=set(node_ids or [node_id])
    rows=[r for rule in report.get('rules',[]) if rule_id is None or str(rule.get('rule_id'))==str(rule_id) for r in rule.get('results',[]) if r.get('node_id') in targets]
    values={r.get('status') for r in rows}
    for value in ['ERROR','VIOLATION','UNKNOWN','PASS','NOT_APPLICABLE']:
        if value in values:return value,rows
    return 'UNKNOWN',rows

def _subtree(ir,target):
    nodes={n['id']:n for n in ir['nodes']};found=set();queue=[target]
    while queue:
        node_id=queue.pop()
        if node_id in found or node_id not in nodes:continue
        found.add(node_id);queue.extend(nodes[node_id]['children'])
    return found

def _view(ir,target):
    nodes={n['id']:n for n in ir['nodes']}
    node=nodes.get(target,{})
    parents={c:n['id'] for n in ir['nodes'] for c in n['children']}
    context=[];current=target
    for _ in range(4):
        parent=nodes.get(parents.get(current),{})
        if not parent:break
        for child in parent['children']:
            item=nodes.get(child,{})
            if item.get('kind') in {'Heading','Paragraph','Caption'} and item.get('text'):
                context.append({'kind':item['kind'],'text':item['text'][:5000]})
        current=parent['id']
    return {'node':node,'context':context[:6]}

def _metrics(records):
    negatives=[r for r in records if r['expected']=='VIOLATION']
    controls=[r for r in records if r['expected']=='PASS']
    nr=sum(r['correct'] for r in negatives);pr=sum(r['correct'] for r in controls)
    rates=[nr/len(negatives) if negatives else 0,pr/len(controls) if controls else 0]
    return {'cases':len(records),'negative_cases':len(negatives),'controls':len(controls),
        'strict_correct_negatives':nr,'strict_correct_controls':pr,
        'strict_balanced_accuracy':sum(rates)/2,
        'mutant_detection_rate':sum(r['after']=='VIOLATION' for r in negatives)/len(negatives) if negatives else 0,
        'control_false_positive_rate':sum(r['after']=='VIOLATION' or r['before']=='VIOLATION' for r in controls)/len(controls) if controls else 0,
        'unknown':sum('UNKNOWN' in {r['before'],r['after']} for r in records),
        'errors':sum('ERROR' in {r['before'],r['after']} for r in records),
        'strict_errors':sum(not r['correct'] for r in records)}

def evaluate_cases(package,cases,runner,cache=None):
    cache={} if cache is None else cache
    records=[];failures=[]
    for case in cases:
        oracle=load(case['oracle_path'])
        if oracle.get('valid') is not True or oracle.get('status') not in {'PASS','VIOLATION'}:
            raise FeedbackError('unverified benchmark oracle')
        target=oracle.get('target_node_id',case.get('target_node_id'))
        original=load(case['original_ir_path']);mutant=load(case['ir_path'])
        validate_ir(original);validate_ir(mutant)
        outputs=[]
        for ir in [original,mutant]:
            key=(package['manifest']['version_id'],ir_hash(ir))
            if key not in cache:
                try:cache[key]=runner(package,copy.deepcopy(ir))
                except BudgetExceeded:raise
                except Exception as error:cache[key]={'_execution_error':type(error).__name__,'rules':[]}
            outputs.append(cache[key])
        before,before_rows=_actual(outputs[0],target,package['program_spec']['rule_id'],_subtree(original,target))
        after,after_rows=_actual(outputs[1],target,package['program_spec']['rule_id'],_subtree(mutant,target))
        expected=oracle['status']
        correct=before=='PASS' and after==expected
        record={'id':case['id'],'expected':expected,'before':before,'after':after,'correct':correct,
            'target_node_id':target,'parent_group':case['parent_group'],
            'context_origin':case.get('context_origin'),'evidence_domain':case.get('evidence_domain')}
        records.append(record)
        if not correct:
            failures.append({**record,'original':_view(original,target),'mutant':_view(mutant,target),
                'actual_original':before_rows[:20],'actual_mutant':after_rows[:20],
                'label_evidence':{k:v for k,v in oracle.items() if k not in {'status','valid'}},
                'failure_types':(['false_positive_original'] if before=='VIOLATION' else [])+
                    (['false_negative'] if expected=='VIOLATION' and after!='VIOLATION' else [])+
                    (['false_positive_mutant'] if expected=='PASS' and after=='VIOLATION' else [])+
                    (['insufficient_or_execution'] if {before,after}&{'ERROR','UNKNOWN','NOT_APPLICABLE'} else [])})
    return {'metrics':_metrics(records),'records':records,'failures':failures}

def run_feedback_loop(task,manifest_path,*,client,output_dir,runner,model=None,max_rounds=5,
                      control=None,allow_model_refinement=True,initial_package=None,candidate_validator=None,regression_policy=None,initial_candidate=None,defer_test=False):
    if type(max_rounds) is not int or not 1<=max_rounds<=5:raise FeedbackError('max rounds must be 1..5')
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    manifest=load(manifest_path)
    if manifest.get('schema_version')!='paper-benchmark/2.0' or manifest.get('status') not in {None,'complete'}:
        raise FeedbackError('benchmark is not a complete frozen protocol')
    fingerprint=_fingerprint(manifest_path,manifest)
    frozen={'benchmark_sha256':fingerprint,'task_sha256':digest(task),'max_rounds':max_rounds,
            'allow_model_refinement':bool(allow_model_refinement),
            'initial_version':initial_package['manifest']['version_id'] if initial_package else None,
            'regression_policy':regression_policy,'initial_candidate_sha256':digest(initial_candidate) if initial_candidate else None,'defer_test':bool(defer_test)}
    frozen_path=output_dir/'frozen.json'
    if frozen_path.exists() and load(frozen_path)!=frozen:raise FeedbackError('frozen experiment inputs changed')
    groups={}
    for case in manifest['cases']:
        old=groups.setdefault(case['parent_group'],case['split'])
        if old!=case['split']:raise FeedbackError('parent group leaks across splits')
    if not frozen_path.exists():write_json_atomic(frozen_path,frozen,exclusive=True)
    result_file=output_dir/('selected.json' if defer_test else 'complete.json')
    if result_file.exists():return load(result_file)
    cases=[c for c in manifest['cases'] if str(c['rule_id'])==str(task['rule_id'])]
    split={s:[c for c in cases if c['split']==s] for s in ['feedback','validation','test']}
    if any(not split[s] for s in split):raise FeedbackError('all three disjoint sets are required')
    previous=None;feedback=[];best=None;best_score=-1;baseline=None;rounds=[];cache={};stop_reason='round_limit'
    for index in range(max_rounds):
        if control is not None and control.snapshot()['freeze']:
            stop_reason='frozen';break
        folder=output_dir/f'round-{index:03d}';folder.mkdir(exist_ok=True)
        checkpoint=folder/'round.json'
        if checkpoint.exists():
            record=load(checkpoint);rounds.append(record)
            if record.get('package_path'):
                package=load_program(record['package_path']);previous=package;model=package['model']
                if index==0:baseline=package
                feedback=load(folder/'feedback.json')['failures']
                if record['validation_score']>best_score:
                    best_score=record['validation_score'];best=(package,record)
                if not feedback:stop_reason='feedback_converged';break
            else:feedback=record['failures']
            continue
        try:
            if index==0 and initial_candidate is not None:
                from .programs import build_program,save_program
                from .model_runtime import base_model,extend_model
                candidate_model=copy.deepcopy(model or base_model())
                if initial_candidate.get('model_patch',{}).get('node_types'):
                    candidate_model=extend_model(candidate_model,initial_candidate['model_patch'])
                package=build_program(initial_candidate,rule_text=task['rule_text'],basis=task['basis'],model=candidate_model)
                if not (folder/'package'/'manifest.json').exists():save_program(package,folder/'package')
                write_json_atomic(folder/'initial-reuse.json',{'raw_sha256':digest(initial_candidate),'generation_call':False})
            elif index==0 and initial_package is not None:
                from .programs import save_program,verify_program
                package=copy.deepcopy(initial_package);verify_program(package)
                if package['input']['rule_text']!=task['rule_text'] or package['input']['basis']!=task['basis'] or package['program_spec']['rule_id']!=str(task['rule_id']):
                    raise FeedbackError('shared initial candidate does not match task')
                if not (folder/'package'/'manifest.json').exists():save_program(package,folder/'package')
                write_json_atomic(folder/'initial-reuse.json',{'version_id':package['manifest']['version_id'],'generation_call':False})
            else:
                package=synthesize_program(task,client,folder,model=model,previous=previous,
                    feedback=feedback[:12],allow_model_refinement=allow_model_refinement)
            if index==0:baseline=package
            fb=evaluate_cases(package,split['feedback'],runner,cache)
            validation=evaluate_cases(package,split['validation'],runner,cache)
            cross=candidate_validator(package) if candidate_validator is not None else {'passed':True,'failures':[]}
            if not isinstance(cross,dict) or type(cross.get('passed')) is not bool:
                raise FeedbackError('invalid cross-rule validation result')
            if not cross['passed']:
                fb['failures']+=cross.get('failures') or [{'failure_types':['cross_rule_regression'],'reason':'cross-rule validation failed'}]
            write_json_atomic(folder/'feedback.json',fb)
            write_json_atomic(folder/'validation-evaluation.json',validation)
            record={'round':index,'status':'evaluated','version_id':package['manifest']['version_id'],
                'model_version':package['model']['version'],'package_path':str((folder/'package').resolve()),
                'feedback_metrics':fb['metrics'],'validation_metrics':validation['metrics'],
                'validation_score':validation['metrics']['strict_balanced_accuracy'] if cross['passed'] else -1,
                'cross_rule_validation':cross}
            write_json_atomic(folder/'package'/'validation.json',{'status':'passed' if cross['passed'] else 'regression_rejected',
                'behavior_evaluated':True,'feedback_metrics':fb['metrics'],'validation_metrics':validation['metrics']})
            previous=package;model=package['model'];feedback=fb['failures']
            if record['validation_score']>best_score:
                best_score=record['validation_score'];best=(package,record)
        except BudgetExceeded:
            stop_reason='budget_limit'
            write_json_atomic(folder/'budget-stop.json',{'status':'budget_exhausted','round':index})
            break
        except Exception as error:
            feedback=[{'failure_types':['compile_or_contract'],'error_type':type(error).__name__,'reason':str(error)[:3000]}]
            if index==0 and initial_candidate is not None:feedback[0]['failed_candidate']=initial_candidate
            record={'round':index,'status':'candidate_failed','failures':feedback}
        write_json_atomic(checkpoint,record);rounds.append(record)
        if record['status']=='evaluated' and not feedback:
            stop_reason='feedback_converged';break
    if not best:
        result={'status':'incomplete','stop_reason':stop_reason,'rounds_completed':len(rounds),'rounds':rounds,
                'best_version':None,'remaining_feedback_errors':len(feedback)}
        write_json_atomic(output_dir/'partial.json',result)
        return result
    if _fingerprint(manifest_path,manifest)!=fingerprint:raise FeedbackError('frozen experiment inputs changed during execution')
    package,record=best
    if stop_reason=='budget_limit':
        result={'status':'incomplete','stop_reason':'budget_limit','rounds_completed':len(rounds),'rounds':rounds,
            'best_version':package['manifest']['version_id'],'best_package_path':record['package_path'],
            'remaining_feedback_errors':record['feedback_metrics']['strict_errors'],'benchmark_sha256':fingerprint}
        write_json_atomic(output_dir/'partial.json',result)
        return result
    if defer_test:
        result={'status':'selected_pending_test','stop_reason':stop_reason,'rounds_completed':len(rounds),'rounds':rounds,
            'initial_version':baseline['manifest']['version_id'] if baseline else None,'best_version':package['manifest']['version_id'],
            'best_package_path':record['package_path'],'remaining_feedback_errors':record['feedback_metrics']['strict_errors'],
            'benchmark_sha256':fingerprint,'deferred_test':True}
        write_json_atomic(result_file,result,exclusive=True)
        return result
    try:
        final_test=evaluate_cases(package,split['test'],runner,cache)
        baseline_test=evaluate_cases(baseline,split['test'],runner,cache) if baseline else {'metrics':None,'records':[]}
    except BudgetExceeded:
        result={'status':'incomplete','stop_reason':'budget_limit_test','rounds_completed':len(rounds),
            'rounds':rounds,'best_version':package['manifest']['version_id'],'best_package_path':record['package_path']}
        write_json_atomic(output_dir/'partial.json',result);return result
    write_json_atomic(output_dir/'test-final.json',final_test)
    write_json_atomic(output_dir/'test-baseline.json',baseline_test)
    result={'status':'completed','stop_reason':stop_reason,'rounds_completed':len(rounds),'rounds':rounds,
        'initial_version':baseline['manifest']['version_id'] if baseline else None,
        'best_version':package['manifest']['version_id'],'best_package_path':record['package_path'],
        'baseline_test':baseline_test['metrics'],'final_test':final_test['metrics'],
        'remaining_feedback_errors':record['feedback_metrics']['strict_errors'],'benchmark_sha256':fingerprint}
    write_json_atomic(result_file,result,exclusive=True)
    return result
