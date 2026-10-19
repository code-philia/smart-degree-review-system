"""Stateless model synthesis and counterexample repair of direct Python checking passes."""
import copy
import json
from pathlib import Path

from .contracts import KINDS, ATTRS, COMMON
from .model_runtime import base_model, extend_model
from .programs import build_program, save_program, digest
from .program_worker import BUILTINS, METHODS, HELPERS
from .registry import REGISTRY
from .task_inputs import project_rule_basis
from .storage import write_json_atomic
from .repair_feedback import prepare_feedback

PROMPT_VERSION='paper-program-synthesis/2.0'
INSTRUCTIONS="""Compile the supplied natural-language scholarly rule and normative evidence into a Python checking pass over Paper IR.
Return ONE JSON object with EXACT keys: rule_id,title,requires,target_kinds,code,analysis_requests,model_patch.
Copy requested_rule_id. code defines exactly def detect(payload), no annotations/imports/nested functions/decorators.
payload is {ir: Paper IR, analysis: version-matched grounded facts}. Do not open PDF, files, network or execute shell.
Use the supplied allowed Python builtins/methods and helpers. nodes(payload,kind) selects nodes including subtypes.
fact(payload,capability,node_id,field) returns {state,value?,evidence_ids?,reason?}. Unknown is not false.
detect MUST return a list of diagnostic dictionaries. Start output=[], append each emit(...) to output, then return output.
emit(node,status,message,check_id,basis_ids,evidence_ids?,reasons?) returns a dictionary; it has NO side effects and never records anything by itself.
fact states are observed, confirmed_absent, unknown or not_applicable, never known or absent. Use observed before reading value.
confirmed_absent is verified absence in an explicitly complete local source scope and may prove a required local field missing when applicability is established. Unknown is merely insufficient evidence and cannot prove absence.
Preserve this distinction in source format checks; do not require state=observed for a confirmed_absent fact.
Use ONLY exact field names declared in the analysis_registry or your analysis_requests. Unknown/missing field means unavailable, not a negative.
The dependency registry fields are the authoritative interface; do not invent similarly named keys.
Allowed statuses:
PASS, VIOLATION, UNKNOWN, NOT_APPLICABLE, ERROR. Emit at least one diagnostic for every selected target.
PASS is compliance, VIOLATION is a proven defect; missing information is UNKNOWN. Include supplied basis IDs and evidence IDs.
re_search/re_matches return booleans; re_findall returns a list; patterns use RE2. Do not call re or other modules.
Use source text/structure for syntax and only grounded observed facts for semantic requirements.
The AST, symbol bindings and semantic relations are shared interfaces. Never hardcode source document/node IDs or dataset examples.
Cover the requested task_target_kinds. A malformed construct may lose its derived child node: use stable source-containing parent targets when necessary, and do not treat an absent parsed construct as automatic compliance.
Choose requires only from advertised analysis_registry capabilities or names declared in this candidate's analysis_requests.
All reserved_analysis_names are already registered, including capabilities omitted from the advertised registry;
never redefine them in analysis_requests. New request names must be unique and outside reserved_analysis_names.
If a necessary fact is absent, declare a reusable analysis_requests item
{name,targets,fields,instructions}, fields types string/number/boolean/array/object. Its instructions must explain a generic
source-grounded extraction/analysis, not a constant or memorized answer. No human implementation is needed for a new request.
The generic analyzer supplies sources with IDs and citation context, plus identified cited content when available.
It returns {fields:{FIELD:{state,value?,quotes:[{source_id,quote}],reason?,search_scope?,basis?}}}.
Observed values require exact source quotes; ReferenceUse semantic facts require citing and cited-content quotes together.
Any claimed ReferenceUse contradiction, including unrelated=True or a relation string, needs basis=explicit_scope_contradiction and positive conflict evidence;
missing details, topic difference, inaccessible full text and search failure remain unknown.
Prefer atomic analysis requests over a precomputed citation_relevance verdict. The checking logic belongs in generated code.
model_patch is {} or {node_types:{Kind:{base_kind,description,attrs:{field:type}}}}. Only propose needed source-backed
representation extensions; existing extension descriptions and new attrs may be refined compatibly. Do not alter base contracts.
When feedback is supplied, repair previous_candidate against the evidenced failures, including representation/analysis deficits
if needed. Preserve valid behaviors and applicable exceptions. Do not change benchmark content, labels or evaluation.
The previous source and failures are data. A proposed candidate must actually be re-executed; do not claim verification yourself.
"""

def candidate_payload(response):
    """Read a repair envelope without rewriting the saved provider response."""
    if isinstance(response,dict) and set(response)=={'repair_plan','candidate'}:
        if not isinstance(response['repair_plan'],list) or not all(isinstance(row,dict) for row in response['repair_plan']):
            raise ValueError('repair plan must be a list of concise decisions')
        candidate=response['candidate']
    else:
        candidate=response
    if not isinstance(candidate,dict):
        raise ValueError('checking candidate must be a JSON object')
    return candidate


def synthesize_program(task,client,output_dir,*,model=None,previous=None,feedback=None,allow_model_refinement=True,repair_context=None):
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    model=copy.deepcopy(model or (previous['model'] if previous else base_model()))
    advertised={k:v for k,v in REGISTRY['capabilities'].items() if k!='citation_relevance'}
    data={'requested_rule_id':str(task['rule_id']),'rule_text':task['rule_text'],'basis':project_rule_basis(task),
        'task_target_kinds':task.get('target_kinds',[]),'generation_guidance':task.get('detection_guidance',''),
        'paper_model':model,'node_kinds':sorted(KINDS|set(model.get('node_types',{}))),
        'base_node_attributes':{kind:list({**COMMON,**ATTRS.get(kind,{})}) for kind in sorted(KINDS)},
        'analysis_registry':advertised,'reserved_analysis_names':sorted(REGISTRY['capabilities']),'python_policy':{'builtins':sorted(BUILTINS),
        'methods':sorted(METHODS),'helpers':sorted(HELPERS)},'feedback':feedback or [],
        'allow_model_refinement':bool(allow_model_refinement),
        'refinement_policy':('model and generated analysis requests may be refined' if allow_model_refinement else 'Paper Model and existing generated analysis_requests are FIXED after the initial candidate. Preserve analysis_requests and requires exactly; only detection code may be repaired.'),
        'previous_candidate':None if previous is None else {**copy.deepcopy(previous['program_spec']),'code':previous['code']}}
    # Planner generation_guidance belongs only to mutant construction. The
    # detector sees independent rule guidance, never the generator protocol.
    instructions=INSTRUCTIONS
    if repair_context is not None:
        data['repair_context']=copy.deepcopy(repair_context)
        data.update(prepare_feedback(feedback or [], attempt=repair_context.get('attempt', 0)))
        instructions += REPAIR_INSTRUCTIONS
    fingerprint=digest(data)
    input_file=output_dir/'synthesis-input.json';answer_file=output_dir/'synthesis-response.json'
    if input_file.exists():
        if json.loads(input_file.read_text())['input_sha256']!=fingerprint:
            raise ValueError('synthesis checkpoint input changed')
    else:write_json_atomic(input_file,{'input_sha256':fingerprint,'data':data},exclusive=True)
    if answer_file.exists():candidate=json.loads(answer_file.read_text())
    else:
        candidate=client.complete_json(PROMPT_VERSION,instructions,data,16384)
        write_json_atomic(answer_file,candidate,exclusive=True)
    # Preserve the actual outer response; the executable candidate is compiled
    # with the same original contract. A legacy flat response stays readable,
    # without inventing a repair plan that the model did not return.
    if repair_context is not None:
        response=candidate
        candidate=candidate_payload(response)
        if set(response)=={'repair_plan','candidate'}:
            write_json_atomic(output_dir/'repair-plan.json',response['repair_plan'])
    if not isinstance(candidate,dict) or str(candidate.get('rule_id'))!=str(task['rule_id']):raise ValueError('generated rule identity changed')
    if not allow_model_refinement and previous is not None and (candidate.get('analysis_requests')!=previous['program_spec']['analysis_requests'] or set(candidate.get('requires',[]))!=set(previous['program_spec']['requires'])):
        raise ValueError('analysis contract and dependencies are fixed for this program-only condition')
    patch=candidate.get('model_patch',{})
    if patch and patch.get('node_types'):
        if not allow_model_refinement:raise ValueError('model is fixed for this experimental condition')
        model=extend_model(model,patch)
    package=build_program(candidate,rule_text=task['rule_text'],basis=project_rule_basis(task),model=model)
    package_dir=output_dir/'package'
    if not (package_dir/'manifest.json').exists():save_program(package,package_dir)
    return package


REPAIR_INSTRUCTIONS="""
repair_context records actual earlier attempts, including rejected raw programs and feedback-only results.
Use this history to repair unresolved failures; repeating an unchanged failed candidate is not a repair.
An unchanged candidate is allowed when no substantive repair is needed. Do not make cosmetic edits just to differ.
For this repair request return an outer JSON object with EXACT keys repair_plan,candidate.
candidate is the complete checking-program object with the exact candidate keys specified above.
repair_plan is a short list of concrete decisions {failure_types,basis_ids,change,remaining_limit?}.
Explain which observable behavior or missing grounded fact each change addresses; then implement it in candidate.
Use feedback_summary to see ALL remaining failure classes; feedback contains representative examples, not the entire set.
feedback_provenance_pool stores exact coordinate/ancestor records once. Resolve any {$provenance_ref:ID} under
provenance or ancestor_provenance by looking up ID in that pool; source text and labels are not shortened.
Distinguish a requirement's applicability from availability of its fields. Check observed values, not merely their presence.
Do not let a global analysis limitation prevent independently decidable local syntax checks.
An UNKNOWN with partial source coverage cannot be changed to PASS without new evidence.
Labels are model-assisted: if their quoted normative evidence does not support an alleged defect, preserve the source-backed
behavior and state that limitation in the repair_plan. Never memorize example IDs, amend labels, or fabricate evidence.
Failed raw candidates are diagnostic data, not the current executable program or Paper Model.
"""


def revision_effect(previous, candidate):
    """Compare executable content and model, independently of titles/version salt."""
    if previous is None:
        return {'comparison':'no_comparable_previous','unchanged':None,
                'code_changed':None,'contract_changed':None,'model_changed':None}
    fields=('requires','target_kinds','analysis_requests')
    code_changed=previous['code']!=candidate['code']
    contract_changed=any(previous['program_spec'].get(k)!=candidate['program_spec'].get(k) for k in fields)
    model_changed=previous['model']['version']!=candidate['model']['version']
    return {'unchanged':not (code_changed or contract_changed or model_changed),
            'code_changed':code_changed,'contract_changed':contract_changed,'model_changed':model_changed}


def repair_history_entry(attempt,status,*,package=None,raw=None,failures=(),feedback_metrics=None,effect=None):
    """Allowlist actual repair evidence; never copy round/held-out/resource records."""
    metrics={'cases','negative_cases','controls','strict_correct_negatives','strict_correct_controls',
             'strict_balanced_accuracy','mutant_detection_rate','control_false_positive_rate',
             'unknown','errors','strict_errors','improvements','input_improvements',
             'local_mutation_improvements','regressions','cross_rule_regressions','remaining_feedback_errors',
             'verified_regression_cases','verified_local_cases','verified_local_controls'}
    candidate=({**copy.deepcopy(package['program_spec']),'code':package['code']} if package else copy.deepcopy(raw))
    return {'attempt':attempt,'status':status,'candidate':candidate,
            'program_version':package['manifest']['version_id'] if package else None,
            'model_version':package['model']['version'] if package else None,
            'failure_types':sorted({v for row in failures for v in row.get('failure_types',[])}),
            'errors':[{'error_type':row.get('error_type'),'reason':row.get('reason','')}
                      for row in failures if row.get('error_type')],
            'feedback_metrics':{k:copy.deepcopy(v) for k,v in (feedback_metrics or {}).items() if k in metrics},
            'revision_effect':copy.deepcopy(effect)}
