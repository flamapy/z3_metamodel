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
    solver = z3.Solver()
    solver.add(model.constraints)

    configurations = []
    n_configs = 0
    while solver.check() == z3.sat:
        m = solver.model()
        config_elements = {}
        block = []

        for feature, feature_info in model.features.items():
            selected = m.evaluate(feature_info.sel, model_completion=True)
            if feature_info.ftype == FeatureType.BOOLEAN:  # boolean feature
                value = z3.is_true(selected)
            else:  # typed feature
                if z3.is_true(selected):
                    value = m.evaluate(feature_info.val, model_completion=True)
                    block.append(feature_info.val != value)  # block the value in the next iter.
                    if feature_info.ftype == FeatureType.INTEGER:
                        value = value.as_long()
                    elif feature_info.ftype == FeatureType.REAL:
                        value = value.as_decimal(Z3Model.DEFAULT_PRECISION)
                    elif feature_info.ftype == FeatureType.STRING:
                        value = value.as_string()
                else:
                    value = False  # not selected
            config_elements[feature] = value
            block.append(feature_info.sel != selected)  # block this value in the next iteration
        n_configs += 1
        config = Configuration(config_elements)
        #print(f'Config. {n_configs}: {config.elements}')
        configurations.append(config)
        solver.add(z3.Or(block))  # block this solution

    return configurations
