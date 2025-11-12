from typing import Any, cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import CoreFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model


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


def get_core_features(model: Z3Model) -> list[Any]:
    solver = z3.Solver(ctx=model.ctx)
    solver.add(model.constraints)

    core_features = []
    if solver.check() == z3.sat:
        for feature, feature_info in model.features.items():
            variable = feature_info.sel
            if solver.check([z3.Not(variable)]) == z3.unsat:
                core_features.append(feature)
    return core_features
