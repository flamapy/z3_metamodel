import logging
from typing import Callable, cast, Optional
from multiprocessing import Queue

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import ConfigurationsNumber
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.fm_metamodel.models import FeatureType


LOGGER = logging.getLogger(__name__)


class Z3ConfigurationsNumber(ConfigurationsNumber):
    """Compute all solutions of a z3 model."""

    def __init__(self) -> None:
        self._result: int = 0
        self._partial_configuration: Optional[Configuration] = None
        self.report_progress: Optional[Callable] = None
    
    def set_progress_reporter(self, report_progress: Callable) -> None:
        self.report_progress = report_progress

    def set_partial_configuration(self, configuration: Configuration) -> None:
        self._partial_configuration = configuration
        
    def get_result(self) -> int:
        return self._result

    def get_configurations_number(self) -> int:
        return self.get_result()

    def execute(self, model: VariabilityModel) -> 'Z3ConfigurationsNumber':
        z3_model = cast(Z3Model, model)
        self._result = configurations(z3_model, self._partial_configuration, self.report_progress)
        return self


def configurations(model: Z3Model, 
                   partial_configuration: Optional[Configuration] = None,
                   report_progress: Optional[Callable] = None) -> int:
    solver = z3.Solver(ctx=model.ctx)

    # 1. Add the model constraints to the solver
    solver.add(model.constraints)

    # 2. Create constraints for the given partial configuration (if any)
    if partial_configuration is not None:
        if partial_configuration.is_full:
            LOGGER.warning("Full configuration provided.")
            return []  # Full configuration provided
        config_constraints = []
        for feature_name, feature_value in partial_configuration.elements.items():
            if feature_name not in model.features:
                LOGGER.error(f"ERROR: the feature '{feature_name}' of the partial "\
                               "configuration does not exist in the Z3 model.")
                return []
            feature_info = model.features[feature_name]
            constraints = Z3Model.create_feature_constraints(feature_value, 
                                                             feature_info, 
                                                             model.ctx)
            config_constraints.extend(constraints)
        solver.add(config_constraints)

    # 3. Enumerate all solutions
    configurations = []
    while solver.check() == z3.sat:
        m = solver.model()
        config_elements = {}
        block = []

        for feature, feature_info in model.features.items():
            sel = feature_info.sel
            selected = m.evaluate(sel, model_completion=True)
            block.append(sel != selected)  # block this value in the next iteration
            if feature_info.ftype == FeatureType.BOOLEAN:  # boolean feature
                value = z3.is_true(selected)
            else:  # typed feature
                if z3.is_true(selected):
                    val_expr = feature_info.val
                    if val_expr is None:
                        raise ValueError(f'Feature {feature} has no value expression.')
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
        config = Configuration(config_elements)
        configurations.append(config)
        if report_progress is not None:
            report_progress(len(configurations))
        solver.add(z3.Or(block))  # block this solution
    return len(configurations)
