from typing import cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Satisfiable
from flamapy.metamodels.z3_metamodel.models import Z3Model


class Z3Satisfiable(Satisfiable):
    """Checks if a z3 model is satisfiable (valid)."""

    def __init__(self) -> None:
        self._result: bool = False

    def get_result(self) -> bool:
        return self._result

    def is_satisfiable(self) -> bool:
        return self.get_result()

    def execute(self, model: VariabilityModel) -> 'Z3Satisfiable':
        z3_model = cast(Z3Model, model)
        self._result = is_satisfiable(z3_model)
        return self


def is_satisfiable(model: Z3Model) -> bool:
    solver = z3.Solver(ctx=model.ctx)
    solver.add(model.constraints)
    return solver.check() == z3.sat
