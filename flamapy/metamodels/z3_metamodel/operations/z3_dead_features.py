from typing import Any, cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import DeadFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model


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
    solver = z3.Solver(ctx=model.ctx)
    solver.add(model.constraints)

    dead_features = []
    if solver.check() == z3.sat:
        for feature, feature_info in model.features.items():
            variable = feature_info.sel
            if solver.check([variable]) == z3.unsat:
                dead_features.append(feature)
    return dead_features
