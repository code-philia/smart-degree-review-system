"""Evidence-aware expressions with independent interpreted/generated traversals."""
import ast
from dataclasses import dataclass, field
import re

from .contracts import validate_analysis


@dataclass
class Value:
    value: object = None
    state: str = 'known'
    reasons: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)


def literal(value):
    return Value(value)


class RuntimeContext:
    def __init__(self, ir, analysis):
        self.ir, self.analysis, self.node = ir, analysis, None
        self.evidence_ids={e['id'] for e in analysis['evidence']} | {n['id'] for n in ir['nodes']}

    def field(self, path):
        bits=path.split('.')
        if bits[0]=='node':
            value=self.node
            remaining=bits[1:]
            evidence=[self.node['id']]
        elif bits[0]=='facts' and len(bits)>=3:
            value=self.analysis['results'].get(bits[1],{}).get(self.node['id'],{})
            remaining=bits[2:];evidence=[]
        else:return Value(state='error',reasons=['invalid field path'])
        for bit in remaining:
            if not isinstance(value,dict) or bit not in value:
                return Value(state='unknown',reasons=['field not observed: '+path])
            value=value[bit]
        if isinstance(value,dict) and 'state' in value:
            evidence=value.get('evidence_ids',[])
            if any(e not in self.evidence_ids for e in evidence):
                return Value(state='error',reasons=['unresolved evidence id'])
            if value['state']=='observed':
                if not evidence:return Value(state='unknown',reasons=['observation has no evidence: '+path])
                return Value(value.get('value'),evidence_ids=list(evidence))
            if value['state']=='confirmed_absent':
                if not evidence or not value.get('search_scope'):
                    return Value(state='unknown',reasons=['absence has no scope/evidence'])
                return Value(None,evidence_ids=list(evidence))
            return Value(state='unknown',reasons=[value.get('reason','observation unavailable')])
        return Value(value,evidence_ids=evidence)


def apply_op(op, args):
    reasons=[reason for arg in args for reason in arg.reasons]
    evidence=list(dict.fromkeys(e for arg in args for e in arg.evidence_ids))
    known=[a.value for a in args if a.state=='known']
    if op=='all' and any(v is False for v in known):return Value(False,evidence_ids=evidence,reasons=reasons)
    if op=='any' and any(v is True for v in known):return Value(True,evidence_ids=evidence,reasons=reasons)
    if any(a.state=='error' for a in args):return Value(state='error',reasons=reasons,evidence_ids=evidence)
    if any(a.state!='known' for a in args):return Value(state='unknown',reasons=reasons,evidence_ids=evidence)
    values=[a.value for a in args]
    try:
        if op=='present':result=values[0] is not None and values[0]!='' and values[0]!=[]
        elif op=='all':result=all(v is True for v in values)
        elif op=='any':result=any(v is True for v in values)
        elif op=='not':result=not values[0]
        elif op=='equals':result=values[0]==values[1]
        elif op=='in':result=values[0] in values[1]
        elif op=='contains':result=values[1] in values[0]
        elif op=='matches':
            if values[0] is None:return Value(state='unknown',reasons=['no text available'],evidence_ids=evidence)
            result=bool(re.fullmatch(values[1],values[0]))
        elif op=='length':result=len(values[0])
        elif op=='precedes':
            if values[1] not in values[0] or values[2] not in values[0]:return Value(state='unknown',reasons=['ordered field not observed'],evidence_ids=evidence)
            result=values[0].index(values[1])<values[0].index(values[2])
        elif op=='lt':result=values[0]<values[1]
        elif op=='le':result=values[0]<=values[1]
        elif op=='gt':result=values[0]>values[1]
        elif op=='ge':result=values[0]>=values[1]
        else:return Value(state='error',reasons=['unsupported expression'])
        return Value(result,evidence_ids=evidence,reasons=reasons)
    except (TypeError,ValueError,re.error):
        return Value(state='error',reasons=['incompatible runtime field value'],evidence_ids=evidence)


def evaluate(expr, context):
    op=expr['op']
    if op=='literal':return literal(expr['value'])
    if op=='field':return context.field(expr['path'])
    return apply_op(op,[evaluate(arg,context) for arg in expr['args']])


def select_nodes(ir, kind):
    return [n for n in ir['nodes'] if n['kind']==kind]


def emit(rule_id, check, node, condition, assertion):
    if condition.state=='known' and condition.value is False:status='NOT_APPLICABLE'
    elif condition.state!='known':status='ERROR' if condition.state=='error' else 'UNKNOWN'
    elif condition.value is not True:status='ERROR'
    elif assertion.state!='known':status='ERROR' if assertion.state=='error' else 'UNKNOWN'
    elif assertion.value is True:status='PASS'
    elif assertion.value is False:status='VIOLATION'
    else:status='ERROR'
    return {'rule_id':rule_id,'check_id':check['id'],'node_id':node['id'],'status':status,
            'message':check['message'] if status=='VIOLATION' else None,
            'reasons':list(dict.fromkeys(condition.reasons+assertion.reasons)),
            'evidence_ids':list(dict.fromkeys(condition.evidence_ids+assertion.evidence_ids)),
            'basis':check.get('basis',[]),'provenance':node['provenance']}


def no_targets(ir, rule_id, check):
    coverage_key={'BibliographyEntry':'bibliography','ReferenceUse':'reference_uses','CitationGroup':'reference_uses'}.get(check['target_kind'],check['target_kind'])
    coverage=ir['coverage'].get(coverage_key,{})
    complete=coverage.get('status')=='complete'
    return {'rule_id':rule_id,'check_id':check['id'],'node_id':None,
            'status':'NOT_APPLICABLE' if complete else 'UNKNOWN','message':None,
            'reasons':['no matching targets; '+('covered scope' if complete else 'incomplete extraction coverage')],
            'evidence_ids':[],'basis':check.get('basis',[]),'provenance':[]}


def interpret_rule(rule_ir: dict, ir: dict, analysis: dict) -> list[dict]:
    validate_analysis(ir,analysis)
    context=RuntimeContext(ir,analysis);output=[]
    for check in rule_ir['checks']:
        targets=select_nodes(ir,check['target_kind'])
        if not targets:
            output.append(no_targets(ir,rule_ir['rule_id'],check));continue
        for node in targets:
            context.node=node
            condition=evaluate(check['when'],context)
            assertion=evaluate(check['assert'],context)
            output.append(emit(rule_ir['rule_id'],check,node,condition,assertion))
    return output


def run_generated(code: str, ir: dict, analysis: dict) -> list[dict]:
    from .compiler import generate_code
    parsed=ast.parse(code)
    if not parsed.body or not isinstance(parsed.body[0],ast.Assign):
        raise ValueError('generated code manifest missing')
    try:rule=ast.literal_eval(parsed.body[0].value)
    except (ValueError,TypeError):raise ValueError('invalid generated code manifest') from None
    if code!=generate_code(rule):
        raise ValueError('generated code differs from verified deterministic backend')
    namespace={'__builtins__':{},'validate_analysis':validate_analysis,'RuntimeContext':RuntimeContext,
               'select_nodes':select_nodes,'no_targets':no_targets,'emit':emit,'literal':literal,'apply_op':apply_op}
    exec(compile(code,'<generated-paper-check>','exec'),namespace)
    return namespace['generated_check'](ir,analysis)
