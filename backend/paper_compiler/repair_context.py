"""Private analysis references and target-scoped, feedback-only fact projections."""
from copy import deepcopy

from .contracts import reject_answers

VERSION='paper-feedback-context/1.0'


def attach_feedback_context(report,materialized_ir,analysis):
    """Add private references; do not copy IR/layout or alter scoring diagnostics.

    The checker has already validated these inputs. Reuse its bound hash instead
    of hashing the full IR again. This private field is not a public JSON report.
    """
    bound=analysis.get('paper_ir_sha256')
    if not bound or report.get('paper_ir_sha256')!=bound:
        raise ValueError('feedback context report/analysis hash mismatch')
    if materialized_ir.get('model_version')!=analysis.get('model_version'):
        raise ValueError('feedback context model mismatch')
    return {**report,'_feedback_context':{'schema_version':VERSION,'paper_ir_sha256':bound,
        'model_version':analysis['model_version'],'ir':materialized_ir,'analysis':analysis}}


def _references(value):
    found=set()
    if isinstance(value,dict):
        for key,child in value.items():
            if key in {'evidence_ids','source_evidence_ids'} and isinstance(child,list):
                found.update(v for v in child if isinstance(v,str))
            elif key in {'content_id','work_id'} and isinstance(child,str):found.add(child)
            found.update(_references(child))
    elif isinstance(value,list):
        for child in value:found.update(_references(child))
    return found


def project_feedback_context(report,target_ids,requires=None):
    """Project native analysis fields, never predictions, oracle or full layout.

    requires is an optional exact capability filter; None includes all available
    capabilities for selected nodes. Binding expansion does not guess dependency
    capabilities. Every returned mutable value is independent of the cache.
    """
    context=report.get('_feedback_context')
    if context is None:return None
    if context.get('schema_version')!=VERSION:raise ValueError('unknown feedback context version')
    ir=context['ir'];analysis=context['analysis']
    if ir.get('model_version')!=context['model_version']:raise ValueError('feedback context model changed')
    if report.get('paper_ir_sha256')!=context['paper_ir_sha256']:raise ValueError('feedback context report hash changed')
    if analysis.get('paper_ir_sha256')!=context['paper_ir_sha256'] or analysis.get('model_version')!=context['model_version']:
        raise ValueError('feedback context binding changed')
    if isinstance(target_ids,str) or isinstance(requires,str):raise ValueError('target IDs/capabilities must be collections')
    requested=list(dict.fromkeys(target_ids));allowed=None if requires is None else set(requires)
    nodes={n['id']:n for n in ir['nodes']};selected=set();pending=list(requested)
    while pending:
        nid=pending.pop()
        if nid not in nodes or nid in selected:continue
        selected.add(nid);pending.extend(nodes[nid].get('children',[]))
    bindings=[b for b in analysis.get('bindings',[]) if b.get('use_id') in selected]
    definitions=ir.get('extensions',{}).get('paper_model',{}).get('node_types',{})
    def bibliography(nid):
        kind=nodes.get(nid,{}).get('kind');seen=set()
        while kind in definitions and kind not in seen:
            seen.add(kind);kind=definitions[kind]['base_kind']
        return kind=='BibliographyEntry'
    for binding in bindings:
        if binding.get('status')=='resolved':
            selected.update(nid for nid in binding.get('target_ids',[]) if bibliography(nid))
    results={name:{nid:fields for nid,fields in values.items() if nid in selected}
             for name,values in analysis.get('results',{}).items() if allowed is None or name in allowed}
    results={name:values for name,values in results.items() if values}
    attributes={nid:value for nid,value in analysis.get('node_attributes',{}).items() if nid in selected}
    def coverage(value):return {key:item for key,item in value.items() if key not in nodes or key in selected}
    analysis_coverage=coverage(analysis.get('coverage',{}));ir_coverage=coverage(ir.get('coverage',{}))
    entities={item['id']:item for item in analysis.get('entities',[])}
    entity_ids={eid for eid,item in entities.items()
                if item.get('use_id') in selected or (item.get('target_node_id') in selected and
                   (allowed is None or item.get('capability') in allowed))}
    for edge in analysis.get('edges',[]):
        if edge.get('type')=='identifies' and edge.get('from') in selected and edge.get('to') in entities:
            entity_ids.add(edge['to'])
    needed=_references([results,attributes,bindings,analysis_coverage,ir_coverage])
    evidence={item['id']:item for item in analysis.get('evidence',[])}
    evidence_ids=set()
    # Follow only referenced evidence and anchored identity entities. Do not
    # traverse outgoing graph edges from a shared work to unrelated citations.
    while True:
        before=(len(needed),len(entity_ids),len(evidence_ids))
        entity_ids.update(needed & entities.keys())
        for eid in entity_ids:needed.update(_references(entities[eid]))
        evidence_ids.update(needed & evidence.keys())
        for eid in evidence_ids:needed.update(_references(evidence[eid]))
        endpoints=selected|entity_ids
        edges=[edge for edge in analysis.get('edges',[]) if edge.get('from') in endpoints and edge.get('to') in endpoints]
        needed.update(_references(edges))
        if before==(len(needed),len(entity_ids),len(evidence_ids)):break
    versions=analysis.get('capability_versions',{})
    version_names=versions.keys() if allowed is None else allowed
    result={'schema_version':VERSION,'analysis_schema_version':analysis.get('schema_version'),
        'producer':analysis.get('producer'),'paper_ir_sha256':context['paper_ir_sha256'],
        'model_version':context['model_version'],'capability_versions':{k:v for k,v in versions.items() if k in version_names},
        'target_ids':requested,'nodes':[n for n in ir['nodes'] if n['id'] in selected],
        'results':results,'node_attributes':attributes,'coverage':analysis_coverage,'ir_coverage':ir_coverage,
        'bindings':bindings,'evidence':[item for item in analysis.get('evidence',[]) if item['id'] in evidence_ids],
        'entities':[item for item in analysis.get('entities',[]) if item['id'] in entity_ids],'edges':edges}
    reject_answers(result)
    return deepcopy(result)
