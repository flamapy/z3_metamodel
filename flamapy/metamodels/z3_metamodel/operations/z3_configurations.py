from typing import cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Configurations
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.fm_metamodel.models import FeatureType


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


def configurations(model: Z3Model) -> list[Configuration]:
    context = z3.Context()
    solver = z3.Solver(ctx=context)
    constraints = [ctc.translate(context) for ctc in model.constraints]
    solver.add(constraints)

    configurations = []
    n_configs = 0
    while solver.check() == z3.sat:
        m = solver.model()
        config_elements = {}
        block = []

        for feature, feature_info in model.features.items():
            sel = feature_info.sel.translate(context)  # Translate to the new context
            selected = m.evaluate(sel, model_completion=True)
            block.append(sel != selected)  # block this value in the next iteration
            if feature_info.ftype == FeatureType.BOOLEAN:  # boolean feature
                value = z3.is_true(selected)
            else:  # typed feature
                if z3.is_true(selected):
                    val_expr = feature_info.val
                    if val_expr is None:
                        raise ValueError(f'Feature {feature} has no value expression.')
                    val_expr = val_expr.translate(context)  # Translate to the new context
                    value = m.evaluate(val_expr, model_completion=True)
                    block.append(val_expr != value)  # block the value in the next iter.
                    if feature_info.ftype == FeatureType.INTEGER:
                        value = value.as_long()
                    elif feature_info.ftype == FeatureType.REAL:
                        value = value.as_decimal(Z3Model.DEFAULT_PRECISION)
                    elif feature_info.ftype == FeatureType.STRING:
                        value = value.as_string()
                else:
                    value = False  # not selected
            config_elements[feature] = value
        n_configs += 1
        config = Configuration(config_elements)
        #print(f'Config. {n_configs}: {config.elements}')
        configurations.append(config)
        solver.add(z3.Or(block))  # block this solution
    return configurations
