"""UVL conformance regression suite.

Checks the Z3 backend's satisfiability result against an independently established answer for one
small, hand-verified model per UVL construct/level (Boolean, group cardinality, arithmetic,
aggregate, string, typed features). It is the *ground truth*: every case asserts the correct answer,
with no tolerance for the current open bugs — so until those are fixed this suite is RED on the
cases below, and goes green as each fix lands.

Expected values were computed with an independent reference oracle (enumeration + Z3) and checked by
hand. Models live in ``resources/models/conformance/``.
"""
import os

import pytest

from flamapy.core.exceptions import FlamaException
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import Z3Satisfiable

MODELS = "resources/models/conformance"


def _satisfiable(name: str) -> bool:
    z3_model = FmToZ3(UVLReader(os.path.join(MODELS, name)).transform()).transform()
    return Z3Satisfiable().execute(z3_model).get_result()


# (model, expected_satisfiable). All values are the correct answer; the cases that currently fail
# correspond to open issues (noted inline) and will pass once those are fixed.
CASES = [
    # Boolean
    ("bool_or.uvl", True),
    ("bool_alternative.uvl", True),
    ("bool_requires.uvl", True),
    ("bool_contradiction.uvl", False),
    # group cardinality
    ("group_card_1_2.uvl", True),
    # arithmetic
    ("arith_sum.uvl", True),
    ("arith_div_exact.uvl", True),
    ("div_real.uvl", True),       # 12 / 8 == 1.5 — integer division would make this UNSAT (#3)
    # aggregate: avg divides by the number of SELECTED bearers (#5), so the result is
    # selection-sensitive, not the constant declaring-feature count.
    ("agg_avg_clean.uvl", True),
    ("agg_avg_selected_sat.uvl", True),      # avg(X)==9 only when the optional bearer is selected
    ("agg_avg_selected_unsat.uvl", False),   # avg(X)==5 holds in no configuration
    ("agg_avg_two_optionals.uvl", True),     # avg(X)==6 only when both bearers are selected
    # functions
    ("floor_ceil.uvl", True),     # floor()/ceil() must be supported (#4)
    # string
    ("string_equality.uvl", True),
    ("string_dot_literal.uvl", True),   # literal 'a.b' must be a constant, not a reference (#9)
    # typed features
    ("type_int_bounded.uvl", True),
    ("type_int_unbounded.uvl", True),
    ("type_string_free.uvl", True),
]


@pytest.mark.parametrize("name, expected", CASES)
def test_conformance_satisfiable(name: str, expected: bool):
    assert _satisfiable(name) == expected


# Ill-formed models: the reference oracle reports a model-error (a constraint over an attribute or a
# feature that does not exist). The backend must reject these with a FlamaException, not return a
# satisfiability result for a model it cannot faithfully encode.
INVALID = [
    "invalid_avg_undeclared_attribute.uvl",    # avg() over an attribute no feature declares
    "invalid_dangling_feature_reference.uvl",  # a constraint names a feature that does not exist
    "invalid_dotted_unknown_feature.uvl",      # Feature.Attribute whose feature does not exist
]


@pytest.mark.parametrize("name", INVALID)
def test_conformance_invalid_is_rejected(name: str):
    with pytest.raises(FlamaException):
        _satisfiable(name)
