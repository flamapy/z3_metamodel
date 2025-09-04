from typing import Any, cast

import z3

from flamapy.core.operations import CoreFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.core.models import VariabilityModel



class Z3CoreFeatures(CoreFeatures):

    def __init__(self) -> None:
        self._result: list[Any] = []

    def get_core_features(self) -> list[Any]:
        return self.get_result()

    def get_result(self) -> list[Any]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3CoreFeatures':
        z3_model = cast(Z3Model, model)
        self._result = get_core_features(z3_model)
        return self


def get_core_features(model: Z3Model) -> bool:
    solver = z3.Solver()
    solver.add(model.formulas)
    core_features = []
    if solver.check() == z3.sat:
        for variable in model.get_variables():
            if isinstance(variable, z3.z3.DatatypeRef):  #  is a typed feature
                variable_type = model.get_variable_type(str(variable))
                if solver.check([variable_type.is_None(variable)]) == z3.unsat:
                    core_features.append(variable)
            else:  # boolean feature
                if solver.check([z3.Not(variable)]) == z3.unsat:
                    core_features.append(variable)
    return core_features
