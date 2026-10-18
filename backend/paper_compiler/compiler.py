"""Natural language -> typed RuleSpec -> Rule IR -> deterministic Python backend."""
import hashlib
import json
from pathlib import Path
import re
import re2 as safe_regex

from .contracts import KINDS, ATTRIBUTE_ENUMS
from .storage import json_bytes, write_json_atomic


class CompilationError(ValueError):
    pass


OPS={'present','all','any','not','equals','in','contains','matches','length','lt','le','gt','ge','precedes'}
SPEC_KEYS={'rule_id','title','requires','checks','on_missing'}
PROMPT_VERSION='rule-compiler/1.4'


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
    in_class=False;escaped=False;has_group=False
    for char in pattern:
        if escaped:escaped=False;continue
        if char=='\\':escaped=True;continue
        if char=='[' and not in_class:in_class=True
        elif char==']' and in_class:in_class=False
        elif char in '()' and not in_class:has_group=True
    _fail(not has_group and not re.search(r'\\[1-9]',pattern),'regex groups/backreferences unsupported')
    _fail(not re.search(r'\{\d{6,}',pattern),'regex repetition bound too large')
    try:safe_regex.compile(pattern)
    except safe_regex.error as error:raise CompilationError('invalid regex') from error


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
            _fail(len(bits)==3 and bits[2] in fields,'unknown node attribute: '+path+'; extracted fields must use facts.CAPABILITY.FIELD')
            typ=fields[bits[2]]
            if isinstance(typ,tuple):typ=next((t for t in typ if t is not dict),dict)
            return {str:'string',int:'number',bool:'boolean',list:'array',dict:'object'}[typ]
        _fail(bits[0]=='facts' and len(bits)==3,'field path must address node or a capability field')
        name=bits[1]
        _fail(name in required and name in registry.get('capabilities',{}),'missing or undeclared capability: '+name)
        cap=registry['capabilities'][name]
        _fail(target_kind in cap['targets'],'capability target type mismatch: '+path+' on '+target_kind+'; allowed targets: '+str(cap['targets']))
        _fail(bits[2] in cap['fields'],'unknown capability field: '+path)
        return cap['fields'][bits[2]]
    _fail(op in OPS,'unsupported operation: '+str(op))
    _fail(set(expr)=={'op','args'} and isinstance(expr['args'],list),'invalid operation arguments')
    args=expr['args'];types=[expression_type(a,target_kind,registry,required,depth+1) for a in args]
    if op in {'equals','in','contains'} and len(args)==2:
        for index,arg in enumerate(args):
            if arg.get('op')!='field' or not arg.get('path','').startswith('node.attrs.'):continue
            values=ATTRIBUTE_ENUMS.get(target_kind,{}).get(arg['path'].split('.')[-1])
            other=args[1-index]
            if values and other.get('op')=='literal' and other.get('value') is not None:
                candidates=other['value'] if isinstance(other['value'],list) else [other['value']]
                _fail(all(v in values for v in candidates),'attribute enum requires one of: '+str(values))
    if op in {'all','any'}:
        _fail(1<=len(args)<=100 and all(t=='boolean' for t in types),'boolean arguments required');return 'boolean'
    if op=='not':_fail(types==['boolean'],'not requires boolean');return 'boolean'
    if op=='present':_fail(len(types)==1,'present requires one field');return 'boolean'
    if op=='length':_fail(len(types)==1 and types[0] in {'string','array'},'length requires string or array');return 'number'
    if op=='precedes':
        if len(args)==3 and args[0].get('path')=='facts.bibliography_shape.field_sequence':
            from .registry import FIELD_TYPES
            _fail(all(a.get('op')=='literal' and a.get('value') in FIELD_TYPES for a in args[1:]),'field_sequence takes literal field NAMES, not field values or punctuation')
        _fail(types==['array','string','string'],'precedes requires sequence array and two item names');return 'boolean'
    _fail(len(types)==2,'binary operation requires two arguments')
    if op=='matches':
        _fail(types==['string','string'] and args[1].get('op')=='literal','matches requires text and literal pattern')
        _pattern(args[1]['value'])
    elif op in {'lt','le','gt','ge','precedes'}:_fail(types==['number','number'],'comparison requires numbers')
    elif op=='equals':_fail(types[0]==types[1] or 'null' in types,'equality type mismatch: '+str(types)+'; compare equal types, or use in for scalar membership in an array')
    elif op=='in':_fail(types[1] in {'array','string'},'in requires array or string')
    elif op=='contains':_fail(types[0] in {'array','string'},'contains requires array or string')
    return 'boolean'


def _present_guards(expr):
    if expr.get('op')=='present' and len(expr.get('args',[]))==1 and expr['args'][0].get('op')=='field':return {expr['args'][0]['path']}
    parts=[_present_guards(a) for a in expr.get('args',[]) if isinstance(a,dict)]
    if expr.get('op')=='all':return set().union(*parts)
    if expr.get('op')=='any' and parts:return set.intersection(*parts)
    return set()

def _field_order_operands(expr):
    required=set()
    if expr.get('op')=='precedes' and expr['args'][0].get('path')=='facts.bibliography_shape.field_sequence':
        required={'facts.bibliography_fields.'+a['value'] for a in expr['args'][1:]}
    for child in expr.get('args',[]):
        if isinstance(child,dict):required.update(_field_order_operands(child))
    return required

def validate_rule_ir(rule_ir: dict, registry: dict, *, max_checks=512) -> None:
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
    _fail(isinstance(checks,list) and 1<=len(checks)<=max_checks,'rule needs 1..'+str(max_checks)+' checks')
    ids=set()
    for check in checks:
        _fail(isinstance(check,dict) and set(check)=={'id','target_kind','when','assert','basis','message'},'invalid check fields')
        _fail(isinstance(check['id'],str) and check['id'] and check['id'] not in ids,'duplicate/invalid check ID');ids.add(check['id'])
        _fail(check['target_kind'] in KINDS,'unknown target kind')
        _fail(isinstance(check['message'],str) and isinstance(check['basis'],list),'diagnostic/basis missing')
        for field in ['when','assert']:
            _fail(expression_type(check[field],check['target_kind'],registry,required)=='boolean',field+' must return boolean')
        absent_guards=_field_order_operands(check['assert'])-_present_guards(check['when'])
        _fail(not absent_guards,'field ordering needs present applicability guards for BOTH named fields in when: '+str(sorted(absent_guards)))


def _compiled_expr(expr):
    if expr['op']=='literal':return 'literal('+repr(expr['value'])+')'
    if expr['op']=='field':return 'context.field('+repr(expr['path'])+')'
    return 'apply_op('+repr(expr['op'])+',['+','.join(_compiled_expr(a) for a in expr['args'])+'])'


def generate_code(rule_ir: dict) -> str:
    rule_ir=json.loads(json_bytes(rule_ir))
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


def canonical_expression(expr,depth=0):
    _fail(depth<=24,'expression too deep')
    # Literal sugar is unambiguous; bare field-looking strings are never guessed.
    if not isinstance(expr,dict):
        _fail(not isinstance(expr,str) or not expr.startswith(('facts.','node.')),'field paths require an explicit field expression')
        _literal_type(expr);return {'op':'literal','value':expr}
    if 'args' in expr:return {**expr,'args':[canonical_expression(a,depth+1) for a in expr['args']]}
    return expr


def referenced_capabilities(value):
    names=set()
    if isinstance(value,dict):
        if value.get('op')=='field' and isinstance(value.get('path'),str):
            parts=value['path'].split('.')
            if len(parts)==3 and parts[0]=='facts':names.add(parts[1])
        for child in value.values():names.update(referenced_capabilities(child))
    elif isinstance(value,list):
        for child in value:names.update(referenced_capabilities(child))
    return names


def compile_rule(text: str, basis: list[dict], registry: dict, client, output_dir: Path, *, capability_requests=None, validation_cases=None, expected_rule_id=None, max_attempts=2) -> dict:
    instructions="Compile a natural-language scholarly rule into a typed declarative specification.\nReturn ONE JSON object with EXACT keys rule_id (string), title, requires (capability names), checks, on_missing='UNKNOWN'. Copy requested_rule_id exactly if supplied.\nEvery check has EXACT keys id,target_kind,when,assert,basis (list of supplied basis IDs),message.\nExpressions: {op:'literal',value:...}, {op:'field',path:'node.text' or 'node.attrs.FIELD' or 'facts.CAPABILITY.FIELD'}, {op:OP,args:[EXPRESSION_OBJECTS]}. All constants including regexes and arrays must be literal expressions. Maximum expression nesting 12.\nOP: present,all,any,not,equals,in,contains,matches,length,lt,le,gt,ge,precedes. precedes takes [array, string_item_A, string_item_B] and tests A before B; missing item yields UNKNOWN. lt/le/gt/ge require two NUMBERS, never arrays or strings. Use precedes on field_sequence for field order. field_sequence is an array of FIELD NAMES such as title, type_code, carrier_code, year, not actual field values, slash characters or punctuation. Its two compared items must be literal field names. Inspect punctuation via matches on node.text instead. when and assert must be boolean. Regexes use the linear-time RE2 engine and have no parentheses or backreferences; use character classes or any with separate matches instead of grouping. matches is a full-string match; dot also spans physical line breaks, preserving all source punctuation. Optional absent fields need a present applicability guard.\nCRITICAL: assert is the COMPLIANCE predicate: true=PASS, false=VIOLATION. when selects applicability, never selects a defect. To require existence: when=true and assert=(exists equals true). A defect-named rule does not invert compliance.\nBibliographic fields live at facts.bibliography_fields.title, facts.bibliography_fields.type_code, etc. They are NOT node.attrs.title/type_code. Choose paths from capability_field_paths or the supplied node_attributes only. Use reusable registered fields with the exact declared types, not rule-ID-specific operations. Respect standard modalities, exceptions and resource types. A requirement restricted to electronic resources MUST include facts.bibliography_shape.electronic == true in when. Bibliographic format templates show relative order; they do NOT make every placeholder mandatory. Each precedes check MUST have present guards for BOTH fields in when. node.attrs.resource_type MUST use the supplied enum names, e.g. journal_article, standard, thesis. Bibliographic letter codes J/S/D belong ONLY to facts.bibliography_fields.type_code. Resource type S means a cited standard; type D means a cited thesis. The enclosing document being a thesis does not change the cited resource type. Do not emit Python, SQL, shell or filenames.\nCitation separators are CONDITIONAL: a singleton [1], nonconsecutive [1,3], a range [1-3], and mixed [1,3-5] are all valid. Do not require every citation to contain commas, hyphens or semicolons. Author-year citations may be parenthetical (Smith, 2020) or narrative Smith (2020); use citation_syntax.form. In narrative form no comma is required between the author outside parentheses and the year inside. Numeric ordering applies only when citation_order.system is numeric. Bibliography labels/field order differ by bibliography_shape.system. In author_year bibliography the year immediately follows the author BEFORE the title/container. Checks requiring title/container/publisher to precede year MUST be restricted to numeric bibliography system. This applies across every resource-type clause, even if that clause illustrates only the numeric template. Metadata available_fields is a partial positive set; do not equate unknown availability with absence.\nMissing evidence stays UNKNOWN. A field can be confirmed absent only inside a documented source scope. Conditional required fields require independent proof the source has that field. DOI/URL are not universally mandatory.\nExternal identity requires verified existence or an independently scoped exclusion; failed searches are unknown. Relevance compares a specific citation purpose to source content; global topic mismatch or absent abstract detail is not negative proof.\nIf a required capability is missing, name it in requires; do not replace it with a constant true. On a retry, repair previous_candidate against ALL failure_history entries; do not regenerate an earlier known failure. For separator arrays, optional absence is legal: use empty-array checks or applicability guards rather than requiring membership unconditionally. Repeated use is legal; never assert is_first_use=true for every citation. Independent behavior test cases are withheld; diagnostics from a failed attempt describe constraints, not a new user rule.\n"
    if type(max_attempts)is not int or not 1<=max_attempts<=3:raise CompilationError('invalid compilation attempt limit')
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    from .contracts import ATTRS,COMMON
    advertised_fields=[{'path':'facts.'+name+'.'+field,'type':typ,'targets':cap['targets']} for name,cap in registry['capabilities'].items() for field,typ in cap['fields'].items()]
    failure=None;validation=[];previous_candidate=None;failure_history=[]
    for attempt in range(1,max_attempts+1):
        spec=client.complete_json(PROMPT_VERSION+'/semantic-gate-1',instructions,{'rule_text':text,'basis':basis,'registry':registry,
            'node_attribute_enums':ATTRIBUTE_ENUMS,'node_kinds':sorted(KINDS),'capability_field_paths':advertised_fields,'node_attributes':{kind:sorted({**COMMON,**ATTRS.get(kind,{})}) for kind in KINDS},'requested_rule_id':expected_rule_id,'previous_failure':failure,'previous_candidate':previous_candidate,'failure_history':failure_history},16384)
        write_json_atomic(output_dir/('compile-attempt-'+str(attempt)+'.json'),spec,exclusive=True)
        validation=[]
        try:
            _fail(isinstance(spec,dict) and set(spec)==SPEC_KEYS,'model returned invalid RuleSpec')
            _fail(expected_rule_id is None or spec['rule_id']==expected_rule_id,'rule_id does not match requested identifier')
            _fail(isinstance(spec['requires'],list) and all(isinstance(n,str) for n in spec['requires']), 'invalid dependencies')
            spec={**spec,'requires':sorted(set(spec['requires'])|referenced_capabilities(spec['checks']))}
            missing=set(spec['requires'])-set(registry['capabilities'])
            if missing and capability_requests:
                from .capabilities import ensure_capabilities
                selected=[request for request in capability_requests if request['name'] in missing]
                _fail({request['name'] for request in selected}==missing, 'missing capability request/independent validation')
                registry=ensure_capabilities(selected,registry,client,output_dir/'capabilities')
            rule_ir={'schema_version':'rule-ir/1.0',**spec,'registry_version':registry['version']}
            rule_ir['checks']=[{**c,'when':canonical_expression(c['when']),'assert':canonical_expression(c['assert'])} for c in spec['checks']]
            validate_rule_ir(rule_ir,registry,max_checks=150)
            validation=[]
            if validation_cases:
                from .expressions import interpret_rule,run_generated
                for case in validation_cases:
                    interpreted=interpret_rule(rule_ir,case['ir'],case['analysis'])
                    generated=run_generated(generate_code(rule_ir),case['ir'],case['analysis'])
                    _fail(interpreted==generated,'independent interpreted/generated execution mismatch')
                    statuses={r['status'] for r in interpreted}
                    actual=next((v for v in ['ERROR','VIOLATION','UNKNOWN','PASS','NOT_APPLICABLE'] if v in statuses),'UNKNOWN')
                    passed=actual in case.get('allowed_statuses',[case['status']]);validation.append({'id':case['id'],'passed':passed,'actual':actual})
                    rejected=[{'check_id':r['check_id'],'status':r['status']} for r in interpreted if r['status']==actual]
                    _fail(passed,'independent behavior validation failed for '+case['id']+'; expected '+str(case.get('allowed_statuses',[case['status']]))+'; candidate checks: '+json.dumps(rejected[:20])+'; '+case.get('diagnostic','check applicability, compliance direction, optional fields, bibliography system and evidence semantics'))
        except CompilationError as error:
            failure=str(error);previous_candidate=spec;failure_history.append(failure)
            write_json_atomic(output_dir/('compile-validation-'+str(attempt)+'.json'),{'status':'failed','reason':failure,'cases':validation},exclusive=True)
            if attempt==max_attempts:raise
            continue
        break
    code=generate_code(rule_ir)
    manifest={'schema_version':'rule-package/1.0','compiler_version':PROMPT_VERSION+'/semantic-gate-1',
        'rule_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'standards_sha256':hashlib.sha256(json_bytes(basis)).hexdigest(),
        'registry_sha256':hashlib.sha256(json_bytes(registry)).hexdigest(),
        'rule_ir_sha256':hashlib.sha256(json_bytes(rule_ir)).hexdigest(),
        'code_sha256':hashlib.sha256(code.encode()).hexdigest(),
        'capability_versions':{name:registry['capabilities'][name]['version'] for name in spec['requires']},
        'status':'compiled_candidate_not_activated',
        'validation':{'passed':len(validation),'cases_sha256':hashlib.sha256(json_bytes(validation_cases or [])).hexdigest(),'attempts':attempt}}
    write_json_atomic(output_dir/'input.json',{'rule_text':text,'basis':basis,'registry':registry},exclusive=True)
    write_json_atomic(output_dir/'rulespec.json',spec,exclusive=True)
    write_json_atomic(output_dir/'rule-ir.json',rule_ir,exclusive=True)
    with (output_dir/'checks.py').open('x',encoding='utf-8') as stream:stream.write(code)
    write_json_atomic(output_dir/'manifest.json',manifest,exclusive=True)
    write_json_atomic(output_dir/'validation.json',{'status':'passed' if validation_cases else 'not_behavior_validated','cases':validation},exclusive=True)
    return {'rule_ir':rule_ir,'manifest':manifest,'code':code,'registry':registry}


def compile_partitioned_rule(text,basis,registry,client,output_dir,*,validation_cases=None,expected_rule_id=None,context_basis=None,max_attempts=2):
    """Compile bounded normative clauses independently, then validate their union.

    Subpackages preserve every model output. The union is never enabled unless all
    withheld combined controls pass. Context clauses clarify but do not add checks.
    """
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    _fail(isinstance(basis,list) and 1<=len(basis)<=50,'invalid clause partition count')
    checks=[];requires=set();parts=[];title=None;rid=expected_rule_id
    for index,clause in enumerate(basis):
        part_cases=[]
        for case in validation_cases or []:
            if case['status']=='PASS':part_cases.append({**case,'allowed_statuses':['PASS','NOT_APPLICABLE']})
            elif clause['id'] in case.get('basis_ids',[]):part_cases.append(case)
        part=compile_rule(text+'\nCompile ONLY the focal normative clause '+clause['id']+'. Other supplied clauses are background context. Produce concise atomic checks for this clause; do not repeat checks for other clauses. Do not infer extra requirements.',
            [clause]+list(context_basis or []),registry,client,output_dir/'parts'/str(index+1),expected_rule_id=rid,max_attempts=max_attempts,validation_cases=part_cases)
        rid=part['rule_ir']['rule_id'];title=title or part['rule_ir']['title'];requires.update(part['rule_ir']['requires'])
        checks.extend([{**check,'id':'clause-'+str(index+1)+'-'+check['id']} for check in part['rule_ir']['checks']])
        parts.append(hashlib.sha256(json_bytes(part['manifest'])).hexdigest())
    rule_ir={'schema_version':'rule-ir/1.0','registry_version':registry['version'],'rule_id':rid,'title':title,
        'requires':sorted(requires),'checks':checks,'on_missing':'UNKNOWN'}
    validate_rule_ir(rule_ir,registry);code=generate_code(rule_ir);validation=[]
    from .expressions import interpret_rule,run_generated
    for case in validation_cases or []:
        values=interpret_rule(rule_ir,case['ir'],case['analysis'])
        _fail(values==run_generated(code,case['ir'],case['analysis']),'combined interpreter/backend mismatch')
        statuses={r['status'] for r in values};actual=next((v for v in ['ERROR','VIOLATION','UNKNOWN','PASS','NOT_APPLICABLE'] if v in statuses),'UNKNOWN')
        validation.append({'id':case['id'],'actual':actual,'passed':actual==case['status']})
    passed=all(v['passed'] for v in validation)
    write_json_atomic(output_dir/'combined-validation.json',{'passed':passed,'cases':validation,'candidate_rule_ir':rule_ir},exclusive=True)
    _fail(passed,'combined independent behavior validation failed')
    all_basis=list(basis)+list(context_basis or [])
    manifest={'schema_version':'rule-package/1.0','compiler_version':PROMPT_VERSION+'/partitioned-1',
        'rule_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'standards_sha256':hashlib.sha256(json_bytes(all_basis)).hexdigest(),
        'registry_sha256':hashlib.sha256(json_bytes(registry)).hexdigest(),'rule_ir_sha256':hashlib.sha256(json_bytes(rule_ir)).hexdigest(),
        'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'capability_versions':{n:registry['capabilities'][n]['version'] for n in requires},
        'status':'compiled_candidate_not_activated','partition_manifests':parts,
        'validation':{'passed':len(validation),'cases_sha256':hashlib.sha256(json_bytes(validation_cases or [])).hexdigest(),'attempts':1}}
    write_json_atomic(output_dir/'input.json',{'rule_text':text,'basis':all_basis,'registry':registry},exclusive=True)
    write_json_atomic(output_dir/'rulespec.json',{k:v for k,v in rule_ir.items() if k in SPEC_KEYS},exclusive=True)
    write_json_atomic(output_dir/'rule-ir.json',rule_ir,exclusive=True)
    (output_dir/'checks.py').write_text(code,encoding='utf-8')
    write_json_atomic(output_dir/'manifest.json',manifest,exclusive=True)
    write_json_atomic(output_dir/'validation.json',{'status':'passed' if validation_cases else 'not_behavior_validated','cases':validation},exclusive=True)
    return {'rule_ir':rule_ir,'manifest':manifest,'code':code,'registry':registry}
