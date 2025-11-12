import logging
from typing import cast

import z3 

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import SatisfiableConfiguration
from flamapy.metamodels.configuration_metamodel.models.configuration import Configuration
from flamapy.metamodels.z3_metamodel.models import Z3Model


LOGGER = logging.getLogger(__name__)


class Z3SatisfiableConfiguration(SatisfiableConfiguration):

    def __init__(self) -> None:
        self._result: bool = False
        self._configuration: Configuration = Configuration(elements={})

    def set_configuration(self, configuration: Configuration) -> None:
        self._configuration = configuration

    def get_result(self) -> bool:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3SatisfiableConfiguration':
        z3_model = cast(Z3Model, model)
        self._result = satisfiable_configuration(z3_model, self._configuration)
        return self

    def is_satisfiable(self) -> bool:
        return self.get_result()


def satisfiable_configuration(z3_model: Z3Model, configuration: Configuration) -> bool:
    solver = z3.Solver(ctx=z3_model.ctx)

    # 1. Add the model constraints to the solver
    solver.add(z3_model.constraints)
    # 2. Create constraints for the given configuration
    config_ctcs = []
    if not configuration.is_full:  # Partial configuration: iterate only over configured features
        for feature_name, feature_value in configuration.elements.items():
            if feature_name not in z3_model.features:
                LOGGER.error(f"ERROR: the feature '{feature_name}' of the configuration " \
                             "does not exist in the Z3 model.")
                return False
            feature_info = z3_model.features[feature_name]
            # Create and add the constraints for feature_name with feature_value
            constraints = Z3Model.create_feature_constraints(feature_value, 
                                                             feature_info, 
                                                             z3_model.ctx)
            config_ctcs.extend(constraints)
    else:  # Complete (full) configuration: iterate over all features in the model
        model_features_set = set(z3_model.features.keys())
        config_features_set = set(configuration.elements.keys())
        extra_features = config_features_set - model_features_set
        if extra_features:
            LOGGER.error(f"ERROR: The configuration contains extra features that do not exist "
                         f"in the model: {extra_features}")
            return False
        
        for feature_name, feature_info in z3_model.features.items():
            feature_value = configuration.elements.get(feature_name, False)
            # Create and add the constraints for feature_name with feature_value
            constraints = Z3Model.create_feature_constraints(feature_value, 
                                                             feature_info, 
                                                             z3_model.ctx)
            config_ctcs.extend(constraints)

    # 3. Add the configuration constraints to the solver
    solver.add(config_ctcs)

    # 4. Check satisfiability
    return solver.check() == z3.sat
