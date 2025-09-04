from typing import Any, cast

import z3

from flamapy.core.operations import DeadFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.core.models import VariabilityModel



class Z3DeadFeatures(DeadFeatures):

    def __init__(self) -> None:
        self._result: list[Any] = []

    def get_dead_features(self) -> list[Any]:
        return self.get_result()

    def get_result(self) -> list[Any]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3DeadFeatures':
        z3_model = cast(Z3Model, model)
        self._result = get_dead_features(z3_model)
        return self


def get_dead_features(model: Z3Model) -> list[Any]:
    solver = z3.Solver()
    solver.add(model.formulas)
    dead_features = []
    if solver.check() == z3.sat:
        for variable in model.get_variables():
            if isinstance(variable, z3.z3.DatatypeRef):  #  is a typed feature
                variable_type = model.get_variable_type(str(variable))
                if solver.check([variable_type.is_Some(variable)]) == z3.unsat:
                    dead_features.append(str(variable))
            else:  # boolean feature
                if solver.check([variable]) == z3.unsat:
                    dead_features.append(str(variable))
    return dead_features
