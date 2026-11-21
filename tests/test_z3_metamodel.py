import pytest

from flamapy.core.exceptions import FlamaException
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3ConfigurationsNumber,
    Z3AttributeOptimization
)
from flamapy.metamodels.z3_metamodel.operations.interfaces import OptimizationGoal


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
    ('resources/models/uvl_models/icecream_attributes.uvl', True),
    ('resources/models/uvl_models/group_cardinalities.uvl', True),
    # Division must be real (12 / 8 == 1.5); integer division would make this UNSAT.
    ('resources/models/uvl_models/real_division.uvl', True),
    # floor(10.5) == 10 and ceil(10.5) == 11 must be supported, not rejected.
    ('resources/models/uvl_models/floor_ceil.uvl', True),
    # A string literal containing '.' must be a constant, not parsed as Feature.Attribute.
    ('resources/models/uvl_models/string_literal_with_dot.uvl', True)
])
def test_z3_satisfiable(path: str, expected: bool):
    z3_model = _read_model(path)
    result = Z3Satisfiable().execute(z3_model).get_result()
    assert result == expected

@pytest.mark.parametrize("path, expected", [
    ('resources/models/uvl_models/fm02_integer_bounded.uvl', 9),
    ('resources/models/uvl_models/fm03_integer_conditional_bounded.uvl', 4),
    ('resources/models/uvl_models/fm04_integer_dead_feature.uvl', 3),
    ('resources/models/uvl_models/fm06_string_bounded.uvl', 6),
    ('resources/models/uvl_models/fm07_string_conditional_bounded.uvl', 5),
    ('resources/models/uvl_models/fm09_real_bounded.uvl', 6),
    ('resources/models/uvl_models/fm10_real_conditional_bounded.uvl', 3),
    ('resources/models/uvl_models/icecream_attributes.uvl', 15),
    ('resources/models/uvl_models/group_cardinalities.uvl', 16),
    ('resources/models/uvl_models/mutex.uvl', 6)
])
def test_nconfigs(path: str, expected: int):
    z3_model = _read_model(path)
    n_configs = Z3ConfigurationsNumber().execute(z3_model).get_result()
    assert n_configs == expected

@pytest.mark.parametrize("path, expected", [
    ('resources/models/uvl_models/icecream_attributes.uvl', 7)
])
def test_pareto_front_nconfigs(path: str, expected: int):
    z3_model = _read_model(path)
    attribute_optimization_op = Z3AttributeOptimization()
    attributes = {'Price': OptimizationGoal.MAXIMIZE,
                  'Cost': OptimizationGoal.MINIMIZE}
    attribute_optimization_op.set_attributes(attributes)
    configs = attribute_optimization_op.execute(z3_model).get_result()
    assert len(configs) == expected


_AGGREGATE_MODEL = ("features\n    Root\n        mandatory\n            Integer f1\n"
                    "            Integer f2\n            A {Price 2}\n            B\n"
                    "constraints\n    {constraint}\n")


@pytest.mark.parametrize("constraint, message", [
    # z3_metamodel#8: sum/avg take (attribute[, rootFeature]), not a list of feature values.
    ("avg(f1, f2) == 1.0", "'f1' is not a declared attribute"),
    ("sum(f1, f2) > 0", "'f1' is not a declared attribute"),
    ("sum(Price, Nope) > 0", "'Nope' is not a feature"),
])
def test_malformed_aggregate_is_rejected(tmp_path, constraint, message):
    path = tmp_path / "aggregate.uvl"
    path.write_text(_AGGREGATE_MODEL.replace("{constraint}", constraint))
    with pytest.raises(FlamaException, match=message):
        _read_model(str(path))


@pytest.mark.parametrize("constraint, expected", [
    ("sum(Price, A) == 2", True),
    ("avg(Price, A) == 2.0", True),
    ("sum(Price) == 2", True),
    # Price is declared in the model but by no feature under B: the sum is 0.
    ("sum(Price, B) == 0", True),
    ("sum(Price, B) > 0", False),
])
def test_aggregate_over_attribute(tmp_path, constraint, expected):
    path = tmp_path / "aggregate.uvl"
    path.write_text(_AGGREGATE_MODEL.replace("{constraint}", constraint))
    assert Z3Satisfiable().execute(_read_model(str(path))).get_result() == expected


_AVG_MODEL = """features
    Root
        optional
            A {X 12}
            B {X 6}
            C
constraints
    {constraint}
"""


@pytest.mark.parametrize("constraint, expected", [
    # z3_metamodel#5: avg divides by the *selected* features declaring the attribute.
    ("avg(X) == 12", True),    # {A}
    ("avg(X) == 9", True),     # {A, B}
    ("avg(X) == 6", True),     # {B} only: {A} would be 12 / 1, not 12 / 2
    ("avg(X) == 6 & A", False),
    ("avg(X) == 4", False),
    # With no declaring feature selected the average is undefined: the constraint is false.
    ("avg(X) == 0", False),
    ("avg(X) == 12 & !A & !B", False),
    ("!(avg(X) == 12) & !A & !B", False),
    # Real division: (12 + 6) / 2 compared with a non-integer, and 12 / 1 with an integer.
    ("avg(X) > 8.5 & avg(X) < 9.5", True),
])
def test_avg_over_selected_features(tmp_path, constraint, expected):
    path = tmp_path / "avg.uvl"
    path.write_text(_AVG_MODEL.replace("{constraint}", constraint))
    assert Z3Satisfiable().execute(_read_model(str(path))).get_result() == expected


def test_avg_integer_attributes_use_real_division(tmp_path):
    path = tmp_path / "avg.uvl"
    path.write_text("features\n    Root\n        mandatory\n            A {X 1}\n"
                    "            B {X 2}\nconstraints\n    avg(X) == 1.5\n")
    assert Z3Satisfiable().execute(_read_model(str(path))).get_result() is True


_TYPED_OPERAND_MODEL = """features
    Root
        optional
            Scoop {Price 2}
            B
            Integer I
            String S
constraints
    {constraint}
"""


@pytest.mark.parametrize("constraint, message", [
    # A Boolean feature has no value: it used to reach Z3 as None ('parser error').
    ("Scoop <= 3", "Boolean feature 'Scoop' cannot be used with '<='"),
    ("Scoop + 1 > 0", "Boolean feature 'Scoop' cannot be used with '\\+'"),
    ("I == Scoop", "Boolean feature 'Scoop' cannot be used with '=='"),
    # None == None / None != None made these a silent tautology / contradiction.
    ("Scoop == B", "Boolean feature 'Scoop' cannot be used with '=='"),
    ("Scoop != B", "Boolean feature 'Scoop' cannot be used with '!='"),
    ("len(Scoop) > 0", "len needs a String feature or attribute: 'Scoop' is Boolean"),
    ("len(I) > 0", "len needs a String feature or attribute: 'I' is Integer"),
])
def test_untyped_operand_is_rejected(tmp_path, constraint, message):
    path = tmp_path / "operand.uvl"
    path.write_text(_TYPED_OPERAND_MODEL.replace("{constraint}", constraint))
    with pytest.raises(FlamaException, match=message):
        _read_model(str(path))


@pytest.mark.parametrize("constraint, expected", [
    ("Scoop <=> B", True),
    ("Scoop => B & !B", True),
    ("Scoop & !Scoop", False),
    ("I > 1 & Scoop", True),
    ("I + 1 <= 3 & I > 2", False),
    ("Scoop.Price <= 3", True),
    ("len(S) == 3", True),
    ("S == 'abc'", True),
])
def test_typed_operand_is_accepted(tmp_path, constraint, expected):
    path = tmp_path / "operand.uvl"
    path.write_text(_TYPED_OPERAND_MODEL.replace("{constraint}", constraint))
    assert Z3Satisfiable().execute(_read_model(str(path))).get_result() == expected


_FLOOR_CEIL_MODEL = """features
    Root
        mandatory
            Integer I
            Real R
            String S
            B {Price 10.5, Name 'x'}
constraints
    {constraint}
"""


@pytest.mark.parametrize("constraint, expected", [
    # floor/ceil of a typed feature (not only of an attribute).
    ("R == 2.5 & floor(R) == 2 & ceil(R) == 3", True),
    ("R == 2.5 & floor(R) == 3", False),
    ("R == -2.5 & floor(R) == -3 & ceil(R) == -2", True),
    ("I == 7 & floor(I) == 7 & ceil(I) == 7", True),
    ("floor(B.Price) == 10 & ceil(B.Price) == 11", True),
])
def test_floor_ceil(tmp_path, constraint, expected):
    path = tmp_path / "floor_ceil.uvl"
    path.write_text(_FLOOR_CEIL_MODEL.replace("{constraint}", constraint))
    assert Z3Satisfiable().execute(_read_model(str(path))).get_result() == expected


@pytest.mark.parametrize("constraint, message", [
    ("floor(B) == 1", "floor needs a numeric feature or attribute: 'B' is"),
    ("ceil(S) == 1", "ceil needs a numeric feature or attribute: 'S' is"),
    ("floor(B.Name) == 1", "floor needs a numeric feature or attribute"),
])
def test_floor_ceil_non_numeric_is_rejected(tmp_path, constraint, message):
    path = tmp_path / "floor_ceil.uvl"
    path.write_text(_FLOOR_CEIL_MODEL.replace("{constraint}", constraint))
    with pytest.raises(FlamaException, match=message):
        _read_model(str(path))
