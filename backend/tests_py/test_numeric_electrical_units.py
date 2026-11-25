"""Electrical measurements remain source-backed without admitting material IDs."""
import pytest

import numeric_consistency as n
from test_numeric_source_contract import source_structure


@pytest.mark.parametrize('text,expected', [
    ('NiCoP-3:3和NiFeP-3:3仅需242 mV和330 mV的过电位。', ['242', '330']),
    ('电解槽仅需1.79 V电压即可实现1.0 A cm-2的电流密度。', ['1.79', '1']),
    ('Fe0.5-NiCrSe在175mV下输出1000mA/cm2。', ['175', '1000']),
    ('电池电压为1.697 V，电流为20 μA和30µA。', ['1.697', '20', '30']),
    ('The cell needs 242 mV at 1.0 A cm−2.', ['242', '1']),
    ('电位为-175mV，电流从10mA变化到20mA。', ['175', '10', '20']),
])
def test_explicit_electrical_units_admit_only_source_measurements(text, expected):
    candidates, _ = n.numeric_candidates(text)
    assert [r['value'] for r in candidates] == expected
    for row in candidates:
        assert text[row['start']:row['end']].replace('1.0', '1') == row['value']


@pytest.mark.parametrize('text', [
    'NiCoP-3:3和Fe0.5-NiCrSe。', 'NCFN-350-3与GPT4V、Model20A。',
    '使用第2章和参考文献[3]。', '型号为242mVModel和330A_test。',
])
def test_electrical_unit_support_does_not_admit_identifiers_or_indexes(text):
    assert n.numeric_candidates(text)[0] == []


def test_electrical_measurement_passes_strict_structure_source_validation():
    _, model, context, structure = source_structure('本文提出电催化材料。电解槽仅需1.79 V电压。')
    structure['declarations'][0].update(number='1.79', metric='电池电压', unit='V')
    resolved = n.resolve_structure(structure, context, model)
    assert n.validate_structure(resolved, context, model)
    structure['declarations'][0]['number'] = '1.80'
    with pytest.raises(n.ContractError, match='numeric value.*source'):
        n.validate_structure(n.resolve_structure(structure, context, model), context, model)
