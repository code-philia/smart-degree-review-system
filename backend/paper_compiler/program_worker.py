"""Pure generated Python execution: credentials, files and network are not exposed."""
import ast
import builtins
import json
import re2
import resource
import sys

BUILTINS = {'len','str','int','float','bool','list','dict','set','tuple','sum','min','max',
            'abs','round','sorted','range','enumerate','zip','all','any','isinstance'}
METHODS = {'get','split','rsplit','splitlines','strip','lstrip','rstrip','lower','upper',
           'casefold','count','startswith','endswith','replace','join','find','rfind',
           'items','keys','values','append','extend','isdigit','isalpha','isalnum',
           'setdefault','update','index','insert','pop','copy'}
HELPERS = {'nodes','fact','emit','re_search','re_matches','re_findall'}
DENIED = (ast.Import,ast.ImportFrom,ast.ClassDef,ast.While,ast.AsyncFunctionDef,ast.Await,
          ast.Global,ast.Nonlocal,ast.Delete,ast.With,ast.AsyncWith,ast.Yield,ast.YieldFrom,
          ast.Try,ast.Raise,ast.Lambda)

ERROR_PREFIX = 'PAPER_PROGRAM_ERROR/1 '
ERROR_MESSAGE_LIMIT = 1000
ERROR_LINE_LIMIT = 8
ERROR_RECORD_LIMIT = 16 * 1024

def validate_code(code, entry='detect'):
    if entry not in {'detect','propose','analyze'} or not isinstance(code,str) or len(code)>64000:
        raise ValueError('invalid generated program')
    tree=ast.parse(code)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef):
        raise ValueError('one entry function required')
    fn=tree.body[0]
    if fn.name!=entry or fn.decorator_list or len(fn.args.args)!=1 or fn.args.defaults or fn.args.kw_defaults or fn.args.vararg or fn.args.kwarg or fn.args.posonlyargs or fn.args.kwonlyargs:
        raise ValueError('entry must accept exactly payload')
    if fn.returns or any(a.annotation for a in fn.args.args):
        raise ValueError('annotations are not supported')
    for node in ast.walk(tree):
        if isinstance(node,DENIED):raise ValueError('unsafe syntax')
        if isinstance(node,ast.FunctionDef) and node is not fn:raise ValueError('nested functions forbidden')
        if isinstance(node,ast.Name) and node.id.startswith('_'):raise ValueError(
            f'private names forbidden: {node.id!r} at line {node.lineno}, UTF-8 byte column {node.col_offset+1}')
        if isinstance(node,ast.Attribute) and node.attr not in METHODS:raise ValueError('unsafe attribute')
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name):
                if node.func.id not in BUILTINS|HELPERS:raise ValueError('unsafe call')
            elif not isinstance(node.func,ast.Attribute) or node.func.attr not in METHODS:
                raise ValueError('indirect call forbidden')
            if (isinstance(node.func,ast.Name) and node.func.id in {'re_search','re_matches','re_findall'}
                    and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)):
                options=re2.Options();options.log_errors=False
                try:re2.compile(node.args[0].value,options=options)
                except re2.error as error:
                    raise ValueError(f'invalid RE2 literal pattern at line {node.args[0].lineno}: {str(error)[:ERROR_MESSAGE_LIMIT]}') from error
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Pow,ast.MatMult)):
            raise ValueError('unbounded arithmetic')
    return tree

def nodes(payload, kind):
    definitions=payload.get('ir',{}).get('extensions',{}).get('paper_model',{}).get('node_types',{})
    result=[]
    for node in payload['ir']['nodes']:
        current=node['kind'];seen=set()
        while current not in seen:
            if current==kind:
                result.append(node);break
            seen.add(current)
            current=definitions.get(current,{}).get('base_kind')
            if current is None:break
    return result

def fact(payload, capability, node_id, field):
    return payload.get('analysis',{}).get('results',{}).get(capability,{}).get(node_id,{}).get(
        field,{'state':'unknown','reason':'analysis not available'})

def emit(node, status, message, check_id='rule', basis=None, evidence_ids=None, reasons=None):
    return {'node_id':node['id'],'status':status,'message':message,'check_id':check_id,
            'basis':basis or [],'evidence_ids':evidence_ids or [node['id']],
            'reasons':reasons or []}

def execute(code,payload,entry='detect'):
    tree=validate_code(code,entry)
    namespace={'__builtins__':{n:getattr(builtins,n) for n in BUILTINS},
        'nodes':nodes,'fact':fact,'emit':emit,
        're_search':lambda pattern,text:bool(re2.search(pattern,str(text))),
        're_matches':lambda pattern,text:bool(re2.fullmatch(pattern,str(text))),
        're_findall':lambda pattern,text:re2.findall(pattern,str(text))}
    exec(compile(tree,'<paper-program>','exec'),namespace)
    return namespace[entry](payload)

def main():
    resource.setrlimit(resource.RLIMIT_CPU,(4,4))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    raw=sys.stdin.buffer.read(32*1024*1024+1)
    if len(raw)>32*1024*1024:raise ValueError('input limit')
    data=json.loads(raw)
    result=execute(data['code'],data['payload'],data.get('entry','detect'))
    output=json.dumps(result,ensure_ascii=True,allow_nan=False)
    if len(output)>8*1024*1024:raise ValueError('output limit')
    sys.stdout.write(output)

def _error_record(error):
    lines=set();trace=error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename=='<paper-program>':lines.add(trace.tb_lineno)
        trace=trace.tb_next
    return {'type':type(error).__name__[:64],'message':str(error)[:ERROR_MESSAGE_LIMIT],
            'generated_lines':sorted(lines)[:ERROR_LINE_LIMIT]}


if __name__=='__main__':
    try:main()
    except Exception as error:
        try:
            record=json.dumps(_error_record(error),ensure_ascii=True,allow_nan=False,separators=(',',':'))
            sys.stderr.write('\n'+ERROR_PREFIX+record+'\n')
        except Exception:
            sys.stderr.write('generated program execution rejected\n')
        sys.exit(2)
