import logging
from typing import cast, Any

import z3 

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import SatisfiableConfiguration
from flamapy.metamodels.configuration_metamodel.models.configuration import Configuration
from flamapy.metamodels.fm_metamodel.models import FeatureType
from flamapy.metamodels.z3_metamodel.models.z3_model import Z3Model, FeatureInfo


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
    context = z3.Context()
    solver = z3.Solver(ctx=context)

    # 1. Add the model constraints to the solver
    solver.add([c.translate(context) for c in z3_model.constraints])

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
            constraints = _create_feature_constraints(feature_value, feature_info, context)
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
            constraints = _create_feature_constraints(feature_value, feature_info, context)
            config_ctcs.extend(constraints)

    # 3. Add the configuration constraints to the solver
    solver.add(config_ctcs)

    # 4. Check satisfiability
    return solver.check() == z3.sat


def _create_feature_constraints(feature_value: Any, 
                                feature_info: FeatureInfo,
                                context: z3.Context) -> list[z3.ExprRef]:
    """Create Z3 constraints for a single feature and its configured value."""
    constraints = []
    if feature_value is False:  # Case 1: Feature not selected (False)
        # Constraint: the selection variable (sel) must be False.
        constraints.append(feature_info.sel.translate(context) == z3.BoolVal(False, ctx=context))
    else:  # Case 2: Feature selected (True, Integer, Real, String)
        # Constraint A: the selection variable (sel) must be True.
        sel_var = feature_info.sel.translate(context)
        constraints.append(sel_var == z3.BoolVal(True, ctx=context))
        # Constraint B (Only for Features with value):
        if feature_info.ftype in [FeatureType.INTEGER, FeatureType.REAL, FeatureType.STRING]:
            # The value variable (val) must be equal to the configuration value.
            val_var = feature_info.val.translate(context)
            z3_value = _get_z3_value(feature_value, feature_info.ftype, context)
            constraints.append(val_var == z3_value)    
    return constraints


def _get_z3_value(value: Any, ftype: FeatureType, context: z3.Context) -> z3.ExprRef:
    """Return a Z3 expression for a given Python configuration value."""
    z3_value = None
    if ftype == FeatureType.BOOLEAN:
        z3_value = z3.BoolVal(bool(value), ctx=context)
    elif ftype == FeatureType.INTEGER:
        z3_value = z3.IntVal(int(value), ctx=context)
    elif ftype == FeatureType.REAL:
        # Real values are mapped to RealVal. We use str() to preserve precision.
        z3_value = z3.RealVal(str(value), ctx=context)
    elif ftype == FeatureType.STRING:
        # Strings are mapped to Z3 String
        z3_value = z3.StringVal(str(value), ctx=context)
    else:
        raise ValueError(f"Feature type '{ftype}' not supported for Z3.")
    return z3_value
