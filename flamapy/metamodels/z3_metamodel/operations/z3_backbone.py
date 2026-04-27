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
    solver = z3.Solver(ctx=model.ctx)
    solver.add(model.constraints)

    vars_to_features = {f_info.sel: name for name, f_info in model.features.items()}

    # (out, C) <- SAT(phi)
    if solver.check() != z3.sat:
        return {"core": [], "dead": list(model.features.keys())}

    m = solver.model()
    # C <- filter(C)
    core_candidates = {var for var in vars_to_features.keys() if z3.is_true(m[var])}
    dead_candidates = {var for var in vars_to_features.keys() if z3.is_false(m[var])}

    backbone_core = []
    backbone_dead = []

    while core_candidates or dead_candidates:
        if core_candidates:
            literal = next(iter(core_candidates))
            check_lit = z3.Not(literal)
            is_core = True
        else:
            literal = next(iter(dead_candidates))
            check_lit = literal
            is_core = False

        # (out, S) <- SAT(phi U {not l})
        if solver.check([check_lit]) == z3.unsat:
            if is_core:
                backbone_core.append(vars_to_features[literal])
                solver.add(literal)
                core_candidates.remove(literal)
            else:
                backbone_dead.append(vars_to_features[literal])
                solver.add(z3.Not(literal))
                dead_candidates.remove(literal)
        else:
            new_model = solver.model()
            core_candidates = {var for var in core_candidates if z3.is_true(new_model[var])}
            dead_candidates = {var for var in dead_candidates if z3.is_false(new_model[var])}

    return {"core": backbone_core, "dead": backbone_dead}
