from typing import cast

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Configurations
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.z3_metamodel.models import Z3Model

import z3


class Z3Configurations(Configurations):
    """Compute all solutions of a z3 model."""

    def __init__(self) -> None:
        self._result: list[Configuration] = []

    def get_result(self) -> list[Configuration]:
        return self._result

    def get_configurations(self) -> list[Configuration]:
        return self.get_result()

    def execute(self, model: VariabilityModel) -> 'Z3Configurations':
        z3_model = cast(Z3Model, model)
        self._result = configurations(z3_model)
        return self


def configurations(model: Z3Model) -> bool:
    variables = model.get_variables()
    solver = z3.Solver()
    solver.add(model.formulas)

    configurations = []
    seen_blocks = []
    while solver.check() == z3.sat:
        m = solver.model()
        config_elements = {}

        block = []
        for variable in variables:
            val = m.evaluate(variable, model_completion=True)
            value = val
            if isinstance(val, z3.z3.DatatypeRef):  #  is a typed feature
                variable_type = model.get_variable_type(str(variable))
                if z3.is_true(m.evaluate(variable_type.is_None(variable))):
                    value = False
                else:
                    value = model.get_typed_variable(str(variable))
                    if variable_type == Z3Model.OPTION_INT:
                        value = m.evaluate(value).as_long()
                    elif variable_type == Z3Model.OPTION_REAL:
                        value = m.evaluate(value).as_decimal()
                    elif variable_type == Z3Model.OPTION_STRING:
                        value = m.evaluate(value).as_string()
            else:  # boolean feature
                value = z3.is_true(val)
            config_elements[str(variable)] = value
            block.append(variable != val)

        configurations.append(Configuration(config_elements))
        solver.add(z3.Or(block))  # block this solution

    return configurations

