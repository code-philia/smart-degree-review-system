"""Shared truth-only task projection for detector synthesis and blind oracles."""
import copy


def project_rule_basis(task):
    """Deep-copy normative basis while excluding explicit mutation admission.

    Legacy string bases and string list items remain normative. A basis item
    without a purpose has purpose='rule'. Unknown purposes fail closed so a
    misspelled construction annotation cannot silently reach a detector/judge.
    The generator must continue to receive the complete, unprojected task.
    """
    basis=task.get('basis')
    if isinstance(basis,str):return basis
    if not isinstance(basis,list):raise ValueError('task basis must be text or a list')
    result=[]
    for item in basis:
        if isinstance(item,str):
            result.append(item);continue
        if not isinstance(item,dict):raise ValueError('invalid task basis item')
        purpose=item.get('purpose','rule')
        if purpose not in ('rule','mutation_admission'):
            raise ValueError('unknown task basis purpose: '+str(purpose))
        if purpose=='rule':result.append(copy.deepcopy(item))
    return result


def project_feedback_evidence(oracle):
    """Expose verified truth and source quotes; keep construction/audit raw sealed.

    Oracle reasons may combine rule truth with experimental admission decisions.
    Preserve them in the raw artifact, not in the detector's repair prompt.
    """
    if not isinstance(oracle, dict):
        return {}
    excluded = {row.get('basis_id') for row in
                oracle.get('admission_policy', {}).get('conditions', [])
                if isinstance(row, dict)}
    result = {name: copy.deepcopy(oracle[name]) for name in
              ['target_node_id', 'mutation_type', 'source_edit', 'parent_sha256',
               'mutant_sha256', 'label_protocol', 'label_provenance'] if name in oracle}
    for name in ['label', 'review']:
        judgment = oracle.get(name)
        if not isinstance(judgment, dict):
            continue
        truth = {field: copy.deepcopy(judgment[field]) for field in
                 ['valid', 'original_compliant', 'status', 'basis', 'original_basis']
                 if field in judgment}
        truth['basis_ids'] = [bid for bid in judgment.get('basis_ids', [])
                              if isinstance(bid, str) and bid not in excluded
                              and not bid.startswith('admission:')]
        truth['quotes'] = [copy.deepcopy(quote) for quote in judgment.get('quotes', [])
                           if isinstance(quote, dict) and isinstance(quote.get('source_id'), str)
                           and quote['source_id'] not in excluded
                           and not quote['source_id'].startswith('admission:')]
        result[name] = truth
    return result
