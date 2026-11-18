"""Relations outside the standard shapes still need cardinality constraints."""

import pytest

from flamapy.metamodels.fm_metamodel.models import Feature, FeatureModel, Relation
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.operations import (
    Z3ConfigurationsNumber,
    Z3DeadFeatures,
    Z3Satisfiable,
)
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3


def _model(card_min: int, card_max: int, children: int = 1,
           optional_parent: bool = False) -> FeatureModel:
    root = Feature("Root")
    parent = root
    if optional_parent:
        parent = Feature("Parent", parent=root)
        root.add_relation(Relation(root, [parent], 0, 1))
    members = [Feature(f"F{i}", parent=parent) for i in range(children)]
    parent.add_relation(Relation(parent, members, card_min, card_max))
    return FeatureModel(root)


@pytest.mark.parametrize("card_min,card_max,children,expected", [
    (0, 0, 1, 1),  # Reported [0..0] case.
    (0, 1, 1, 2),  # Standard optional relation.
    (1, 1, 1, 1),  # Standard mandatory relation.
    (1, 2, 1, 1),  # Upper bound above child count.
    (2, 2, 1, 0),  # Impossible lower bound: the model is void.
    (0, 3, 1, 2),  # Extra upper range must not cause an error.
    (0, -1, 1, 2),  # Internal unbounded upper-bound sentinel.
    (0, 0, 2, 1),  # Ordinary two-child cardinality group.
    (0, 0, 0, 1),  # Empty, vacuous relation.
    (1, 1, 0, 0),  # Empty, impossible relation.
])
def test_cardinality_counts(card_min, card_max, children, expected):
    z3_model = FmToZ3(_model(card_min, card_max, children)).transform()
    assert Z3ConfigurationsNumber().execute(z3_model).get_result() == expected
    assert Z3Satisfiable().execute(z3_model).get_result() == (expected > 0)


@pytest.mark.parametrize("cardinality, expected", [
    ("0..0", 1),  # z3_metamodel#2: the child can never be selected
    ("1..2", 1),  # the child is required
    ("2..2", 0),  # impossible: the model is void
    ("0..3", 2),  # the child is optional
])
def test_one_child_cardinality_groups_from_uvl(tmp_path, cardinality, expected):
    path = tmp_path / "one_child.uvl"
    path.write_text(f"features\n    Root\n        [{cardinality}]\n            F0\n")
    z3_model = FmToZ3(UVLReader(str(path)).transform()).transform()
    assert Z3ConfigurationsNumber().execute(z3_model).get_result() == expected
    assert Z3Satisfiable().execute(z3_model).get_result() == (expected > 0)


def test_unary_zero_group_under_optional_parent() -> None:
    z3_model = FmToZ3(_model(0, 0, optional_parent=True)).transform()
    assert Z3ConfigurationsNumber().execute(z3_model).get_result() == 2
    assert Z3DeadFeatures().execute(z3_model).get_result() == ["F0"]
