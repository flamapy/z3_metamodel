from typing import Any, cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Operation
from flamapy.metamodels.z3_metamodel.models import Z3Model


class Z3Backbone(Operation):

    def __init__(self) -> None:
        self._result: dict[str, list[Any]] = {"core": [], "dead": []}

    def get_backbone(self) -> dict[str, list[Any]]:
        return self.get_result()

    def get_result(self) -> dict[str, list[Any]]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3Backbone':
        z3_model = cast(Z3Model, model)
        self._result = get_backbone(z3_model)
        return self


def get_backbone(model: Z3Model) -> dict[str, list[Any]]:
    """Core and dead features: the literals over the selection variables that the model implies.

    `Solver.consequences` computes every implied literal among the given variables in one call,
    inside the solver (models prune the candidates and unsatisfiable cores prove the rest), so no
    per-feature check is needed. It also works on typed models, where the implications may
    depend on the arithmetic and string constraints. An unsatisfiable model has no core
    features and every feature dead, as in the SAT plugin.
    """
    solver = z3.Solver(ctx=model.ctx)
    solver.add(model.constraints)
    selections = [info.sel for info in model.features.values()]
    names = {info.sel.get_id(): name for name, info in model.features.items()}
    status, implied = solver.consequences([], selections)
    if status != z3.sat:
        return {"core": [], "dead": list(model.features.keys())}
    core: list[Any] = []
    dead: list[Any] = []
    for consequence in implied:  # each one is Implies(And(<assumptions>), literal)
        literal = consequence.arg(1)
        if z3.is_not(literal):
            dead.append(names[literal.arg(0).get_id()])
        else:
            core.append(names[literal.get_id()])
    order = {name: index for index, name in enumerate(model.features)}
    return {"core": sorted(core, key=order.__getitem__),
            "dead": sorted(dead, key=order.__getitem__)}
