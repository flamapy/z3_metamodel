"""Backbone (core and dead features) through z3's consequences API, on Boolean and typed models.

The expected values were produced by the previous implementation (one check per candidate
literal) and cross-checked by hand on the small models.
"""
import pytest

from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Backbone,
    Z3CoreFeatures,
    Z3DeadFeatures,
)


MODELS = 'resources/models/uvl_models/'

ELECTRICITY_CORE = ['DATE', 'DAY', 'DAY_NAME', 'DEMAND', 'Electricity_price', 'INFORMATION_TYPE',
                    'MONTH', 'Period', 'USEP', 'YEAR']


@pytest.mark.parametrize('path, core, dead', [
    (MODELS + 'Electricity.uvl', ELECTRICITY_CORE, []),
    (MODELS + 'Electricity_with_deadfeature.uvl', ELECTRICITY_CORE, ['ok']),
    (MODELS + 'Electricity_with_no_deadfeature.uvl', [*ELECTRICITY_CORE, 'ok'], []),
    (MODELS + 'Pizza_z3.uvl',
     ['Dough', 'Normal', 'Pizza', 'Size', 'SpicyLvl', 'Topping'], ['Big', 'Name']),
    (MODELS + 'fm03_integer_conditional_bounded.uvl', ['Container', 'Icecream', 'Scoops'], ['Stick']),
    (MODELS + 'fm04_integer_dead_feature.uvl', ['Container', 'Icecream'], ['Scoops']),
    (MODELS + 'fm13_feature_cardinality_bounded_refactored.uvl', ['R'], ['D']),
    (MODELS + 'numerical_core_feature.uvl', ['Electricity_price', 'Period', 'ok'], []),
    (MODELS + 'group_cardinalities.uvl', ['root'], []),
    (MODELS + 'mutex.uvl', ['root'], []),
])
def test_backbone(path: str, core: list, dead: list):
    z3_model = FmToZ3(UVLReader(path).transform()).transform()
    backbone = Z3Backbone().execute(z3_model).get_result()
    assert sorted(backbone['core']) == sorted(core)
    assert sorted(backbone['dead']) == sorted(dead)
    assert Z3CoreFeatures().execute(z3_model).get_result() == backbone['core']
    assert Z3DeadFeatures().execute(z3_model).get_result() == backbone['dead']


def test_backbone_follows_the_feature_order():
    z3_model = FmToZ3(UVLReader(MODELS + 'Pizza_z3.uvl').transform()).transform()
    order = list(z3_model.features)
    backbone = Z3Backbone().execute(z3_model).get_result()
    assert backbone['core'] == sorted(backbone['core'], key=order.index)
    assert backbone['dead'] == sorted(backbone['dead'], key=order.index)


def test_void_model_has_no_core_and_every_feature_dead():
    z3_model = FmToZ3(UVLReader(MODELS + 'Electricity_unsat.uvl').transform()).transform()
    backbone = Z3Backbone().execute(z3_model).get_result()
    assert backbone['core'] == []
    assert backbone['dead'] == list(z3_model.features)
