import pytest
from collections import defaultdict

from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3ConfigurationsNumber
)


PRECISION = 4


def _read_model(path: str) -> Z3Model:
    z3_model = None  # Initialize z3_model to None
    if path.endswith('.uvl'):
        feature_model = UVLReader(path).transform()
        z3_model = FmToZ3(feature_model).transform()
    else:
        raise ValueError(f"Unsupported file extension for path: {path}")
    return z3_model

@pytest.mark.parametrize("path, expected", [
    ('resources/models/uvl_models/Electricity.uvl', True),
    ('resources/models/uvl_models/fm01_integer_unbounded.uvl', True),
    ('resources/models/uvl_models/fm02_integer_bounded.uvl', True),
    ('resources/models/uvl_models/fm03_integer_conditional_bounded.uvl', True),
    ('resources/models/uvl_models/fm04_integer_dead_feature.uvl', True),
    ('resources/models/uvl_models/fm05_string_unbounded.uvl', True),
    ('resources/models/uvl_models/fm06_string_bounded.uvl', True),
    ('resources/models/uvl_models/fm07_string_conditional_bounded.uvl', True),
    ('resources/models/uvl_models/fm08_real_unbounded.uvl', True),
    ('resources/models/uvl_models/fm09_real_bounded.uvl', True),
    ('resources/models/uvl_models/fm10_real_conditional_bounded.uvl', True),
    ('resources/models/uvl_models/fm11_real_bounded_infinite.uvl', True),
    ('resources/models/uvl_models/fm12_feature_cardinality_bounded.uvl', True),
    ('resources/models/uvl_models/fm13_feature_cardinality_bounded_refactored.uvl', True),
])
def test_z3_satisfiable(path: str, expected: bool):
    z3_model = _read_model(path)
    result = Z3Satisfiable().execute(z3_model).get_result()
    assert result == expected

@pytest.mark.parametrize("path, expected", [
    ('resources/models/uvl_models/fm02_integer_bounded.uvl', 12),
    ('resources/models/uvl_models/fm03_integer_conditional_bounded.uvl', 7),
    ('resources/models/uvl_models/fm04_integer_dead_feature.uvl', 3),
    ('resources/models/uvl_models/fm06_string_bounded.uvl', 9),
    ('resources/models/uvl_models/fm07_string_conditional_bounded.uvl', 7),
    ('resources/models/uvl_models/fm09_real_bounded.uvl', 9),
    ('resources/models/uvl_models/fm10_real_conditional_bounded.uvl', 5),
    ('resources/models/uvl_models/fm12_feature_cardinality_bounded.uvl', 37),
    ('resources/models/uvl_models/fm13_feature_cardinality_bounded_refactored.uvl', 71),
])
def test_nconfigs(path: str, expected: int):
    z3_model = _read_model(path)
    n_configs = Z3ConfigurationsNumber().execute(z3_model).get_result()
    assert n_configs == expected
