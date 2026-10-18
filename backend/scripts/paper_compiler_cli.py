#!/usr/bin/env python3
"""Authenticated host CLI for paper compilation and evaluation; no public compiler endpoint."""
import argparse,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paper_compiler.storage import write_json_atomic,json_bytes
from paper_compiler.budget import BudgetLedger
from paper_compiler.contracts import validate_ir


def parser():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ['build','compile','plan','plan-batch','synthesize','loop','check','batch','evaluate','budget']:
        s=sub.add_parser(name);s.add_argument('--config',default=os.environ.get('PAPER_COMPILER_CONFIG','/data/apps/smart-degree-review/config/paper-model-huawei.env'))
        s.add_argument('--ledger',default='/data/runtime/paper-compiler/budget.sqlite3');s.add_argument('--budget',default='200')
        s.add_argument('--phase',default='pilot');s.add_argument('--phase-budget',default='5');s.add_argument('--cache',default='/data/runtime/paper-compiler')
        s.add_argument('--evidence-snapshot');s.add_argument('--freeze-evidence',action='store_true');s.add_argument('--model-fingerprint');s.add_argument('--offline',action='store_true');s.add_argument('--out',type=Path);s.add_argument('--package',action='append',default=[])
        if name=='build':s.add_argument('--pdf',required=True,type=Path)
        if name in ['plan','plan-batch']:
            s.add_argument('--basis',required=name=='plan',type=Path);s.add_argument('--rule-id',required=name=='plan');s.add_argument('--rule-text',required=name=='plan',type=Path);s.add_argument('--rules',required=name=='plan-batch',type=Path);s.add_argument('--evidence-environments',type=Path);s.add_argument('--allow-constructed',action='store_true');s.add_argument('--paper-model',type=Path)
        if name=='compile':
            s.add_argument('--rule-id',required=True);s.add_argument('--rule-text',type=Path);s.add_argument('--basis',type=Path);s.add_argument('--partitioned',action='store_true')
        if name=='check':
            group=s.add_mutually_exclusive_group(required=True);group.add_argument('--ir',type=Path);group.add_argument('--pdf',type=Path)
            s.add_argument('--analysis',type=Path);s.add_argument('--analysis-out',type=Path);s.add_argument('--stdout-report',action='store_true')
            s.add_argument('--online',action='store_true');s.add_argument('--control-root',default=os.environ.get('PAPER_COMPILER_CONTROL_ROOT','/data/runtime/paper-compiler/online'));s.add_argument('--runtime-resources',type=Path);s.add_argument('--online-max-rounds',type=int,default=2)
        if name in ['batch','evaluate']:s.add_argument('--manifest',required=True,type=Path);s.add_argument('--workers',type=int,default=1)
        if name in ['synthesize','loop']:
            s.add_argument('--task',required=True,type=Path)
            if name=='loop':s.add_argument('--manifest',required=True,type=Path);s.add_argument('--max-rounds',type=int,default=5);s.add_argument('--fixed-model',action='store_true');s.add_argument('--resources',type=Path)
    c=sub.add_parser('control');c.add_argument('--action',required=True,choices=['status','freeze','unfreeze','history','rollback']);c.add_argument('--control-root',default=os.environ.get('PAPER_COMPILER_CONTROL_ROOT','/data/runtime/paper-compiler/online'));c.add_argument('--version')
    return p

def execute(args):
    if args.command=='control':
        from paper_compiler.runtime_control import RuntimeControl
        control=RuntimeControl(args.control_root)
        if args.action=='status':return control.snapshot()
        if args.action in ['freeze','unfreeze']:return control.set_freeze(args.action=='freeze',actor='admin-cli')
        if args.action=='history':return {'events':control.events()}
        if not args.version:raise ValueError('--version required for rollback')
        return control.rollback(args.version,actor='admin-cli')
    if args.command=='budget':return BudgetLedger(args.ledger,args.budget).summary()
    if args.out is None:raise ValueError('--out is required')
    if args.command in ['build','check']:
        if args.out.suffix!='.json':raise ValueError('output must be a new JSON artifact')
        if args.out.exists():raise FileExistsError('output already exists')
    from datetime import datetime,timezone
    args.evidence_snapshot=args.evidence_snapshot or datetime.now(timezone.utc).date().isoformat()
    from paper_compiler.llm import MaasClient,model_fingerprint,public_model_config
    from paper_compiler.evidence import EvidenceGateway
    from paper_compiler.runtime import load_package,check
    from paper_compiler.frontend import build_paper
    from paper_compiler.analysis import enrich
    ledger=BudgetLedger(args.ledger,args.budget)
    client=None if args.offline else MaasClient(args.config,ledger,Path(args.cache)/'model-cache',args.phase,args.phase_budget,max_attempts=1)
    if client and args.model_fingerprint and model_fingerprint(client.config)!=args.model_fingerprint:raise ValueError('effective model configuration changed')
    if args.command in ['plan','plan-batch']:
        from paper_compiler.task_planner import plan_task,plan_tasks
        if client is None:raise ValueError('task planning requires the configured API')
        kwargs={'client':client,'model':json.loads(args.paper_model.read_text()) if args.paper_model else None,
            'allowed_context_origins':('real','constructed') if args.allow_constructed else ('real',),
            'evidence_environments':json.loads(args.evidence_environments.read_text()) if args.evidence_environments else (),
            'output_dir':args.out}
        if args.command=='plan':
            plan_task(args.rule_id,args.rule_text.read_text(),json.loads(args.basis.read_text()),**kwargs)
            return {'status':'planned','task_path':str(args.out/'plan.json'),'budget':ledger.summary()}
        tasks=plan_tasks(json.loads(args.rules.read_text()),**kwargs)
        return {'status':'planned','tasks':len(tasks),'output':str(args.out),'budget':ledger.summary()}
    gateway=None if args.offline else EvidenceGateway(Path(args.cache)/'public-evidence',proxy=os.environ.get('PAPER_COMPILER_PUBLIC_PROXY','http://127.0.0.1:18892'),snapshot_id=args.evidence_snapshot if args.freeze_evidence or args.command in ['batch','evaluate'] else None)
    packages=[load_package(path) for path in args.package]
    def detect_generated(ir,programs,environment=None):
        from paper_compiler.pipeline import detect
        return detect(ir,programs,client=client,gateway=gateway,cache_dir=Path(args.cache),evidence_environment=environment)
    if args.command in ['synthesize','loop']:
        task=json.loads(args.task.read_text())
        if client is None:raise ValueError('program synthesis needs model API')
        if args.command=='synthesize':
            from paper_compiler.synthesis import synthesize_program
            package=synthesize_program(task,client,args.out)
            return {'status':'generated_candidate','manifest':package['manifest'],'budget':ledger.summary()}
        from paper_compiler.feedback_loop import run_feedback_loop
        resources=json.loads(args.resources.read_text()) if args.resources else {}
        result=run_feedback_loop(task,args.manifest,client=client,output_dir=args.out,
            runner=lambda package,ir:detect_generated(ir,[package],resources.get('evidence_environment'))[2],
            max_rounds=args.max_rounds,allow_model_refinement=not args.fixed_model)
        return {**result,'budget':ledger.summary()}

    def build(path):return build_paper(path,client=client)
    def run(path):
        if not packages:raise ValueError('at least one verified --package is required')
        ir=build(path) if path.suffix.lower()=='.pdf' else json.loads(path.read_text());validate_ir(ir)
        if all(p['manifest'].get('schema_version')=='paper-program/2.0' for p in packages):
            return detect_generated(ir,packages)[2]
        a=enrich(ir,packages,client=client,gateway=gateway,cache_dir=Path(args.cache)/'analysis',snapshot_id=args.evidence_snapshot)
        return check(ir,a,packages)
    if args.command=='build':
        ir=build(args.pdf);write_json_atomic(args.out,ir,exclusive=True)
        return {'status':'completed','document_id':ir['document_id'],'output':str(args.out),'nodes':len(ir['nodes']),'budget':ledger.summary()}
    if args.command=='compile':
        from paper_compiler.compiler import compile_rule,compile_partitioned_rule
        from paper_compiler.registry import REGISTRY
        from paper_compiler.standards import RULE_TEXT,basis_for
        from paper_compiler.validation import compiler_controls
        if client is None:raise ValueError('compilation requires the configured model')
        text=args.rule_text.read_text() if args.rule_text else RULE_TEXT[args.rule_id]
        basis=json.loads(args.basis.read_text()) if args.basis else basis_for(args.rule_id)
        fn=compile_partitioned_rule if args.partitioned else compile_rule
        kwargs={}
        if args.partitioned and not args.basis and args.rule_id=='31':
            kwargs['context_basis']=basis[-1:];basis=basis[:-1]
        result=fn(text,basis,REGISTRY,client,args.out,**kwargs,expected_rule_id=args.rule_id,
            validation_cases=compiler_controls(args.rule_id) if not args.rule_text else None)
        return {'status':'compiled_candidate_not_activated','output':str(args.out),'manifest':result['manifest'],'budget':ledger.summary()}
    if args.command=='check':
        if args.analysis_out and (args.analysis_out.exists() or args.analysis_out==args.out):raise FileExistsError('analysis output must be new and distinct')
        if not packages:raise ValueError('at least one verified --package is required')
        ir=build(args.pdf) if args.pdf else json.loads(args.ir.read_text());validate_ir(ir)
        runtime=None
        environment=None
        resources=json.loads(args.runtime_resources.read_text()) if args.runtime_resources else {}
        environment=resources.get('evidence_environment')
        if args.online:
            from paper_compiler.runtime_control import RuntimeControl
            control=RuntimeControl(args.control_root);snapshot=control.snapshot()
            if snapshot.get('active_path'):
                from paper_compiler.pipeline import load_suite
                packages=load_suite(snapshot['active_path'])
            runtime={**snapshot,'mode':'frozen' if snapshot['freeze'] else 'adaptive'}
        generated=[p for p in packages if p['manifest'].get('schema_version')=='paper-program/2.0']
        legacy=[p for p in packages if p not in generated]
        if generated:
            if args.analysis:
                from paper_compiler.model_runtime import apply_model
                from paper_compiler.pipeline import shared_model,rebind
                from paper_compiler.programs import check_programs,digest
                model=shared_model(generated);generated=rebind(generated,model)
                ir=apply_model(ir,model,client=client);a=json.loads(args.analysis.read_text())
                result=check_programs(ir,a,generated)
                result['pipeline_version']=digest([p['manifest'] for p in generated])
            elif args.online and not runtime['freeze'] and client is not None:
                from paper_compiler.online_loop import online_refine
                episode=Path(args.control_root)/'episodes'/__import__('uuid').uuid4().hex
                updated=online_refine(ir,generated,client=client,gateway=gateway,cache_dir=Path(args.cache),
                    control=control,output_dir=episode,resources=resources,max_rounds=args.online_max_rounds)
                ir,a,result=updated['ir'],updated['analysis'],updated['report']
                runtime={**runtime,**updated['runtime']}
            else:ir,a,result=detect_generated(ir,generated,environment)
        else:
            a=json.loads(args.analysis.read_text()) if args.analysis else enrich(ir,legacy,client=client,gateway=gateway,cache_dir=Path(args.cache)/'analysis',snapshot_id=args.evidence_snapshot)
            result=check(ir,a,legacy)
            result['pipeline_version']=hashlib.sha256(json_bytes([p['manifest'] for p in legacy])).hexdigest()
        if generated and legacy:
            old_analysis=enrich(ir,legacy,client=client,gateway=gateway,cache_dir=Path(args.cache)/'analysis',snapshot_id=args.evidence_snapshot)
            old_report=check(ir,old_analysis,legacy);result['rules']+=old_report['rules']
            result['evidence']+=old_report['evidence']
        if runtime is not None:result['runtime']=runtime
        if args.analysis_out:write_json_atomic(args.analysis_out,a,exclusive=True)
        write_json_atomic(args.out,result,exclusive=True)
        if args.stdout_report:
            from paper_compiler.presentation import present
            return present(ir,result)
        return {'status':'completed','output':str(args.out),'rules':[{'rule_id':r['rule_id'],'status':r['status'],'counts':r['counts']} for r in result['rules']],'budget':ledger.summary()}
    if args.command in ['batch','evaluate']:
        sources={str(f.relative_to(Path(__file__).resolve().parents[1])):hashlib.sha256(f.read_bytes()).hexdigest() for f in (Path(__file__).resolve().parents[1]/'paper_compiler').rglob('*') if f.suffix in {'.py','.json'}}
        version=hashlib.sha256(json_bytes({'packages':[p['manifest'] for p in packages],'sources':sources,'model':public_model_config(client.config) if client else 'offline'})).hexdigest()
    if args.command=='batch':
        from paper_compiler.batch import run_batch
        return run_batch(args.manifest,{'pipeline_version':version,'runner':run,'workers':args.workers,'frozen_settings':{'model':client.config.get('MAAS_MODEL_VERSION') if client else 'offline','evidence_snapshot':args.evidence_snapshot}},args.out)
    if args.command=='evaluate':
        from paper_compiler.evaluation import evaluate
        import subprocess,tempfile
        def isolated(path):
            # The child sees a neutral IR path and package/config paths, never an oracle.
            with tempfile.TemporaryDirectory(prefix='detector-',dir=args.out) as folder:
                work=Path(folder);ir=json.loads(Path(path).read_text());validate_ir(ir)
                write_json_atomic(work/'input.json',ir,exclusive=True)
                command=[sys.executable,str(Path(__file__).resolve()),'check','--ir',str(work/'input.json'),'--out',str(work/'result.json'),
                    '--config',args.config,'--ledger',args.ledger,'--budget',args.budget,'--phase',args.phase,'--phase-budget',args.phase_budget,
                    '--cache',args.cache,'--evidence-snapshot',args.evidence_snapshot]
                for package in args.package:command.extend(['--package',package])
                if args.offline:command.append('--offline')
                else:command.extend(['--model-fingerprint',model_fingerprint(client.config),'--freeze-evidence'])
                process=subprocess.run(command,cwd=work,capture_output=True,text=True,timeout=1200)
                if process.returncode or len(process.stdout)>1048576:raise RuntimeError('isolated detector did not complete')
                return json.loads((work/'result.json').read_text())
        isolated.version=version+'@'+args.evidence_snapshot
        return evaluate(args.manifest,args.out,isolated)

def main():
    args=parser().parse_args()
    try:
        result=execute(args);print(json.dumps(result,ensure_ascii=True,allow_nan=False));return 0
    except Exception as error:
        print(json.dumps({'status':'error','error_type':type(error).__name__,'message':'Compiler operation failed; inspect its saved artifacts and budget ledger.'}));return 1
if __name__=='__main__':sys.exit(main())
