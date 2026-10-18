"""Isolated pure capability execution. No credentials, network or file APIs exposed."""
import ast
import contextlib
import io
import json
import math
import resource
import statistics
import sys

ALLOWED_CALLS={'len','str','int','float','bool','list','dict','set','tuple','sum','min','max','abs','round','sorted','range','enumerate','zip','all','any','isinstance'}
ALLOWED_METHODS={'get','split','rsplit','strip','lstrip','rstrip','lower','upper','casefold','count','startswith','endswith','replace','join','find','rfind','items','keys','values','append','extend','isdigit','isalpha','isalnum'}
DENIED_NODES=(ast.Import,ast.ImportFrom,ast.ClassDef,ast.While,ast.AsyncFunctionDef,ast.Await,ast.Global,ast.Nonlocal,ast.Delete,ast.With,ast.AsyncWith,ast.Yield,ast.YieldFrom,ast.Try,ast.Raise,ast.Lambda)


def validate_code(code):
    if not isinstance(code,str) or len(code)>20000:raise ValueError('candidate code size')
    tree=ast.parse(code)
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!='analyze':
        raise ValueError('candidate must contain one analyze function')
    function=tree.body[0]
    if function.decorator_list or len(function.args.args)!=1 or function.args.defaults or function.args.kw_defaults or function.args.vararg or function.args.kwarg:
        raise ValueError('invalid analyze signature')
    if function.returns or any(arg.annotation for arg in function.args.args):raise ValueError('annotations unsupported')
    for node in ast.walk(tree):
        if isinstance(node,DENIED_NODES):raise ValueError('unsafe syntax')
        if isinstance(node,ast.FunctionDef) and node is not function:raise ValueError('nested functions unsupported')
        if isinstance(node,ast.Name) and node.id.startswith('_'):raise ValueError('private name')
        if isinstance(node,ast.Attribute) and node.attr not in ALLOWED_METHODS:raise ValueError('unsafe attribute')
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name):
                if node.func.id not in ALLOWED_CALLS:raise ValueError('unsafe function call')
            elif isinstance(node.func,ast.Attribute):
                if node.func.attr not in ALLOWED_METHODS:raise ValueError('unsafe method call')
            else:raise ValueError('indirect call forbidden')
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Pow,ast.MatMult)):raise ValueError('unbounded arithmetic')
    return tree


def execute(code,payload):
    tree=validate_code(code)
    import builtins
    namespace={'__builtins__':{name:getattr(builtins,name) for name in ALLOWED_CALLS if name!='analyze'}}
    exec(compile(tree,'<validated-capability>','exec'),namespace)
    return namespace['analyze'](payload)


def main():
    resource.setrlimit(resource.RLIMIT_CPU,(2,2))
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    payload=sys.stdin.buffer.read(256*1024+1)
    if len(payload)>256*1024:raise ValueError('input too large')
    data=json.loads(payload)
    result=execute(data['code'],data['payload'])
    output=json.dumps(result,ensure_ascii=True,allow_nan=False)
    if len(output)>128*1024:raise ValueError('output too large')
    sys.stdout.write(output)


if __name__=='__main__':
    try:main()
    except Exception:
        sys.stderr.write('capability execution rejected\n')
        sys.exit(2)
