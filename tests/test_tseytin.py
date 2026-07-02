"""The opt-in Tseytin CNF encoding must yield the same Z3 analysis results as the
default direct translation, and must fall back to the direct translation for any
constraint that is not purely propositional over boolean features."""
import os
import tempfile

from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations.z3_satisfiable import Z3Satisfiable
from flamapy.metamodels.z3_metamodel.operations.z3_configurations import Z3Configurations
from flamapy.metamodels.z3_metamodel.operations.z3_configurations_number import (
    Z3ConfigurationsNumber,
)


# Purely propositional model: every cross-tree constraint is boolean.
_PROP_UVL = """features
    Root {abstract}
        optional
            A
            B
            C
            D
constraints
    (A | B) => (C <=> D)
    A => !B
"""

# All-arithmetic constraints; the Tseytin path must fall back to direct translation.
_ARITH_MODEL = 'resources/models/uvl_models/fm03_integer_conditional_bounded.uvl'


def _build_from_uvl_text(text, cnf_method):
    handle, path = tempfile.mkstemp(suffix='.uvl')
    try:
        with os.fdopen(handle, 'w') as file:
            file.write(text)
        return FmToZ3(UVLReader(path).transform(), cnf_method=cnf_method).transform()
    finally:
        os.remove(path)


def _projected(model):
    configs = Z3Configurations().execute(model).get_result()
    return {frozenset(k for k, v in c.elements.items() if v is True) for c in configs}


def test_tseytin_matches_direct_on_propositional_model() -> None:
    direct = _build_from_uvl_text(_PROP_UVL, 'direct')
    tseytin = _build_from_uvl_text(_PROP_UVL, 'tseytin')

    assert Z3ConfigurationsNumber().execute(direct).get_result() == \
        Z3ConfigurationsNumber().execute(tseytin).get_result()
    assert _projected(direct) == _projected(tseytin)
    assert tseytin.auxiliary_variables  # gates were introduced
    # Auxiliary variables must not have been registered as features.
    assert not set(str(a) for a in tseytin.auxiliary_variables) & set(tseytin.features.keys())


def test_tseytin_falls_back_for_arithmetic_constraints() -> None:
    direct = FmToZ3(UVLReader(_ARITH_MODEL).transform(), cnf_method='direct').transform()
    tseytin = FmToZ3(UVLReader(_ARITH_MODEL).transform(), cnf_method='tseytin').transform()

    # Nothing was propositional, so no auxiliary variables were created.
    assert tseytin.auxiliary_variables == []
    assert Z3Satisfiable().execute(direct).get_result() == \
        Z3Satisfiable().execute(tseytin).get_result()
    assert Z3ConfigurationsNumber().execute(direct).get_result() == \
        Z3ConfigurationsNumber().execute(tseytin).get_result()
