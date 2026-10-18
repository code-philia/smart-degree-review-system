"""Natural language -> typed RuleSpec -> Rule IR -> deterministic Python backend."""
import hashlib
import json
from pathlib import Path
import re

from .contracts import KINDS
from .storage import json_bytes, write_json_atomic


class CompilationError(ValueError):
    pass


OPS={'present','all','any','not','equals','in','contains','matches','length','lt','le','gt','ge'}
SPEC_KEYS={'rule_id','title','requires','checks','on_missing'}
PROMPT_VERSION='rule-compiler/1.0'


def _fail(condition,message):
    if not condition:raise CompilationError(message)


def _literal_type(value):
    if type(value) is bool:return 'boolean'
    if type(value) in (int,float):return 'number'
    if isinstance(value,str):return 'string'
    if isinstance(value,list):return 'array'
    if value is None:return 'null'
    if isinstance(value,dict):return 'object'
    raise CompilationError('unsupported literal')


def _pattern(pattern):
    _fail(isinstance(pattern,str) and len(pattern)<=512,'regex too large')
    # No groups/backreferences: these checks need regular lexical constraints, not an unbounded regex program.
    _fail(not re.search(r'(?<!\\)[()]|\\[1-9]',pattern),'regex groups/backreferences unsupported')
    _fail(not re.search(r'\{\d{6,}',pattern),'regex repetition bound too large')
    try:re.compile(pattern)
    except re.error as error:raise CompilationError('invalid regex') from error


def expression_type(expr, target_kind, registry, required, depth=0):
    _fail(depth<=24 and isinstance(expr,dict),'expression too deep or not an object')
    op=expr.get('op')
    if op=='literal':
        _fail(set(expr)=={'op','value'},'invalid literal fields')
        return _literal_type(expr['value'])
    if op=='field':
        _fail(set(expr)=={'op','path'} and isinstance(expr['path'],str),'invalid field expression')
        path=expr['path'];bits=path.split('.')
        _fail(all(re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*',bit) for bit in bits),'invalid field path')
        if path in {'node.text','node.id','node.kind'}:return 'string'
        if path.startswith('node.attrs.'):
            from .contracts import ATTRS,COMMON
            fields={**COMMON,**ATTRS.get(target_kind,{})}
            _fail(len(bits)==3 and bits[2] in fields,'unknown node attribute')
            typ=fields[bits[2]]
            return 'string' if typ is str else 'number' if typ is int else 'object'
        _fail(bits[0]=='facts' and len(bits)==3,'field path must address node or a capability field')
        name=bits[1]
        _fail(name in required and name in registry.get('capabilities',{}),'missing or undeclared capability: '+name)
        cap=registry['capabilities'][name]
        _fail(target_kind in cap['targets'],'capability target type mismatch')
        _fail(bits[2] in cap['fields'],'unknown capability field: '+path)
        return cap['fields'][bits[2]]
    _fail(op in OPS,'unsupported operation: '+str(op))
    _fail(set(expr)=={'op','args'} and isinstance(expr['args'],list),'invalid operation arguments')
    args=expr['args'];types=[expression_type(a,target_kind,registry,required,depth+1) for a in args]
    if op in {'all','any'}:
        _fail(1<=len(args)<=100 and all(t=='boolean' for t in types),'boolean arguments required');return 'boolean'
    if op=='not':_fail(types==['boolean'],'not requires boolean');return 'boolean'
    if op=='present':_fail(len(types)==1,'present requires one field');return 'boolean'
    if op=='length':_fail(len(types)==1 and types[0] in {'string','array'},'length requires string or array');return 'number'
    _fail(len(types)==2,'binary operation requires two arguments')
    if op=='matches':
        _fail(types==['string','string'] and args[1].get('op')=='literal','matches requires text and literal pattern')
        _pattern(args[1]['value'])
    elif op in {'lt','le','gt','ge'}:_fail(types==['number','number'],'comparison requires numbers')
    elif op=='equals':_fail(types[0]==types[1] or 'null' in types,'equality type mismatch')
    elif op=='in':_fail(types[1] in {'array','string'},'in requires array or string')
    elif op=='contains':_fail(types[0] in {'array','string'},'contains requires array or string')
    return 'boolean'


def validate_rule_ir(rule_ir: dict, registry: dict) -> None:
    _fail(isinstance(rule_ir,dict),'Rule IR must be an object')
    _fail(set(rule_ir)==SPEC_KEYS|{'schema_version','registry_version'},'unknown or missing rule fields')
    _fail(rule_ir['schema_version']=='rule-ir/1.0','unsupported Rule IR version')
    _fail(rule_ir['registry_version']==registry['version'],'capability registry version mismatch')
    _fail(isinstance(rule_ir['rule_id'],str) and bool(rule_ir['rule_id']),'rule_id must be a string')
    _fail(isinstance(rule_ir['title'],str),'title must be a string')
    _fail(rule_ir['on_missing']=='UNKNOWN','missing evidence must remain UNKNOWN')
    required=rule_ir['requires']
    _fail(isinstance(required,list) and all(isinstance(c,str) for c in required),'requires must be a capability list')
    _fail(len(set(required))==len(required),'duplicate capability dependency')
    for cap in required:_fail(cap in registry['capabilities'],'missing capability: '+cap)
    checks=rule_ir['checks']
    _fail(isinstance(checks,list) and 1<=len(checks)<=150,'rule needs 1..150 checks')
    ids=set()
    for check in checks:
        _fail(isinstance(check,dict) and set(check)=={'id','target_kind','when','assert','basis','message'},'invalid check fields')
        _fail(isinstance(check['id'],str) and check['id'] and check['id'] not in ids,'duplicate/invalid check ID');ids.add(check['id'])
        _fail(check['target_kind'] in KINDS,'unknown target kind')
        _fail(isinstance(check['message'],str) and isinstance(check['basis'],list),'diagnostic/basis missing')
        for field in ['when','assert']:
            _fail(expression_type(check[field],check['target_kind'],registry,required)=='boolean',field+' must return boolean')


def _compiled_expr(expr):
    if expr['op']=='literal':return 'literal('+repr(expr['value'])+')'
    if expr['op']=='field':return 'context.field('+repr(expr['path'])+')'
    return 'apply_op('+repr(expr['op'])+',['+','.join(_compiled_expr(a) for a in expr['args'])+'])'


def generate_code(rule_ir: dict) -> str:
    lines=['RULE_IR = '+repr(rule_ir),'','def generated_check(ir, analysis):',
           '    validate_analysis(ir, analysis)','    context = RuntimeContext(ir, analysis)','    output = []']
    for index,check in enumerate(rule_ir['checks']):
        lines+=['    check = RULE_IR[\'checks\']['+str(index)+']',
                '    targets = select_nodes(ir, '+repr(check['target_kind'])+')',
                '    if not targets:',
                '        output.append(no_targets(ir, RULE_IR[\'rule_id\'], check))',
                '    for node in targets:', '        context.node = node',
                '        condition = '+_compiled_expr(check['when']),
                '        assertion = '+_compiled_expr(check['assert']),
                '        output.append(emit(RULE_IR[\'rule_id\'], check, node, condition, assertion))']
    return '\n'.join(lines+['    return output',''])


def compile_rule(text: str, basis: list[dict], registry: dict, client, output_dir: Path, *, capability_requests=None) -> dict:
    instructions="""You compile a natural-language scholarly rule to a typed declarative specification.
Return one JSON object with EXACT keys rule_id (string), title, requires (capability names), checks, on_missing='UNKNOWN'.
Each check has EXACT keys id, target_kind, when, assert, basis (list of supplied basis IDs), message.
Expressions: {op:'literal',value:...}; {op:'field',path:'node.text' or 'node.attrs.FIELD' or 'facts.CAPABILITY.FIELD'};
{op: OP,args:[expressions...]}. OP is present, all, any, not, equals, in, contains, matches, length, lt, le, gt, ge.
when and assert must be boolean. Regex patterns are literal strings without capture groups/backreferences; compose alternatives with any.
Use reusable registered facts, not rule-ID-specific operations. Do not emit Python, SQL, shell or filenames.
Use exact field names and target types from the supplied registry. Respect applicable standard modalities and exceptions.
Observed missing evidence remains UNKNOWN. Absence can only be a violation when its observation is confirmed absent.
External identity: verified existence passes; only independently scoped exclusion can fail; failed searches are unknown.
Relevance: compare this citation purpose to cited content; do not use global topic similarity or lack of abstract detail as negative proof.
If required capability is missing, list it in requires so compilation can report the gap; never replace it with a literal true.
"""
    spec=client.complete_json(PROMPT_VERSION,instructions,{'rule_text':text,'basis':basis,'registry':registry,
                'node_kinds':sorted(KINDS)},8192)
    _fail(isinstance(spec,dict) and set(spec)==SPEC_KEYS,'model returned invalid RuleSpec')
    _fail(isinstance(spec['requires'],list) and all(isinstance(n,str) for n in spec['requires']), 'invalid dependencies')
    missing=set(spec['requires'])-set(registry['capabilities'])
    if missing and capability_requests:
        from .capabilities import ensure_capabilities
        selected=[request for request in capability_requests if request['name'] in missing]
        _fail({request['name'] for request in selected}==missing, 'missing capability request/independent validation')
        registry=ensure_capabilities(selected,registry,client,Path(output_dir)/'capabilities')
    rule_ir={'schema_version':'rule-ir/1.0',**spec,'registry_version':registry['version']}
    validate_rule_ir(rule_ir,registry)
    code=generate_code(rule_ir)
    manifest={'schema_version':'rule-package/1.0','compiler_version':PROMPT_VERSION,
        'rule_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'standards_sha256':hashlib.sha256(json_bytes(basis)).hexdigest(),
        'registry_sha256':hashlib.sha256(json_bytes(registry)).hexdigest(),
        'rule_ir_sha256':hashlib.sha256(json_bytes(rule_ir)).hexdigest(),
        'code_sha256':hashlib.sha256(code.encode()).hexdigest(),
        'capability_versions':{name:registry['capabilities'][name]['version'] for name in spec['requires']},
        'status':'compiled_candidate_not_activated'}
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    write_json_atomic(output_dir/'input.json',{'rule_text':text,'basis':basis,'registry':registry},exclusive=True)
    write_json_atomic(output_dir/'rulespec.json',spec,exclusive=True)
    write_json_atomic(output_dir/'rule-ir.json',rule_ir,exclusive=True)
    with (output_dir/'checks.py').open('x',encoding='utf-8') as stream:stream.write(code)
    write_json_atomic(output_dir/'manifest.json',manifest,exclusive=True)
    return {'rule_ir':rule_ir,'manifest':manifest,'code':code}
