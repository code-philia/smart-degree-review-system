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
    for name in ['build','compile','check','batch','evaluate','budget']:
        s=sub.add_parser(name);s.add_argument('--config',default=os.environ.get('PAPER_COMPILER_CONFIG','/data/apps/smart-degree-review/config/paper-model-huawei.env'))
        s.add_argument('--ledger',default='/data/runtime/paper-compiler/budget.sqlite3');s.add_argument('--budget',default='1000')
        s.add_argument('--phase',default='pilot');s.add_argument('--phase-budget',default='5');s.add_argument('--cache',default='/data/runtime/paper-compiler')
        s.add_argument('--evidence-snapshot');s.add_argument('--offline',action='store_true');s.add_argument('--out',type=Path);s.add_argument('--package',action='append',default=[])
        if name=='build':s.add_argument('--pdf',required=True,type=Path)
        if name=='compile':
            s.add_argument('--rule-id',required=True);s.add_argument('--rule-text',type=Path);s.add_argument('--basis',type=Path);s.add_argument('--partitioned',action='store_true')
        if name=='check':
            group=s.add_mutually_exclusive_group(required=True);group.add_argument('--ir',type=Path);group.add_argument('--pdf',type=Path)
            s.add_argument('--analysis',type=Path);s.add_argument('--analysis-out',type=Path);s.add_argument('--stdout-report',action='store_true')
        if name in ['batch','evaluate']:s.add_argument('--manifest',required=True,type=Path);s.add_argument('--workers',type=int,default=1)
    return p

def execute(args):
    if args.command=='budget':return BudgetLedger(args.ledger,args.budget).summary()
    if args.out is None:raise ValueError('--out is required')
    if args.command in ['build','check']:
        if args.out.suffix!='.json':raise ValueError('output must be a new JSON artifact')
        if args.out.exists():raise FileExistsError('output already exists')
    from datetime import datetime,timezone
    args.evidence_snapshot=args.evidence_snapshot or datetime.now(timezone.utc).date().isoformat()
    from paper_compiler.llm import MaasClient
    from paper_compiler.evidence import EvidenceGateway
    from paper_compiler.runtime import load_package,check
    from paper_compiler.frontend import build_paper
    from paper_compiler.analysis import enrich
    ledger=BudgetLedger(args.ledger,args.budget)
    client=None if args.offline else MaasClient(args.config,ledger,Path(args.cache)/'model-cache',args.phase,args.phase_budget)
    gateway=None if args.offline else EvidenceGateway(Path(args.cache)/'public-evidence',proxy=os.environ.get('PAPER_COMPILER_PUBLIC_PROXY','http://127.0.0.1:18892'))
    packages=[load_package(path) for path in args.package]
    def build(path):return build_paper(path,client=client)
    def run(path):
        if not packages:raise ValueError('at least one verified --package is required')
        ir=build(path) if path.suffix.lower()=='.pdf' else json.loads(path.read_text());validate_ir(ir)
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
        a=json.loads(args.analysis.read_text()) if args.analysis else enrich(ir,packages,client=client,gateway=gateway,cache_dir=Path(args.cache)/'analysis',snapshot_id=args.evidence_snapshot)
        result=check(ir,a,packages)
        if args.analysis_out:write_json_atomic(args.analysis_out,a,exclusive=True)
        write_json_atomic(args.out,result,exclusive=True)
        if args.stdout_report:
            from paper_compiler.presentation import present
            return present(ir,result)
        return {'status':'completed','output':str(args.out),'rules':[{'rule_id':r['rule_id'],'status':r['status'],'counts':r['counts']} for r in result['rules']],'budget':ledger.summary()}
    if args.command in ['batch','evaluate']:
        sources={str(f.relative_to(Path(__file__).resolve().parents[1])):hashlib.sha256(f.read_bytes()).hexdigest() for f in (Path(__file__).resolve().parents[1]/'paper_compiler').rglob('*') if f.suffix in {'.py','.json'}}
        version=hashlib.sha256(json_bytes({'packages':[p['manifest'] for p in packages],'sources':sources})).hexdigest()
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
