import logging
from typing import Any, cast

import z3

from flamapy.core.operations import FalseOptionalFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.fm_metamodel.models import FeatureModel
from flamapy.core.models import VariabilityModel, VariabilityElement
from flamapy.core.exceptions import FlamaException


LOGGER = logging.getLogger('PySATFalseOptionalFeatures')


class Z3FalseOptionalFeatures(FalseOptionalFeatures):

    def __init__(self) -> None:
        self._result: list[Any] = []

    def get_false_optional_features(self) -> list[Any]:
        return self.get_result()

    def get_result(self) -> list[Any]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3FalseOptionalFeatures':
        z3_model = cast(Z3Model, model)
        try:
            feature_model = cast(FeatureModel, model.original_model)
        except FlamaException:
            LOGGER.exception("The transformation didn't attach the source model, "
                             "which is required for this operation.")
        self._result = get_false_optional_features(z3_model, feature_model)
        return self


def get_false_optional_features(model: Z3Model, feature_model: FeatureModel) -> list[Any]:
    solver = z3.Solver()
    solver.add(model.formulas)
    false_optional_features = []

    real_optional_features = [f for f in feature_model.get_features()
                              if not f.is_root() and not f.is_mandatory()]

    for feature in real_optional_features:
        parent_feature = feature.get_parent()
        parent_variable = model.get_boolean_variable(parent_feature.name)
        variable = model.get_boolean_variable(feature.name)
        if isinstance(variable, z3.z3.DatatypeRef):  #  is a typed feature
            variable_type = model.get_variable_type(str(variable))
            if solver.check([parent_variable, variable_type.is_None(variable)]) == z3.unsat:
                false_optional_features.append(feature.name)
        else:  # boolean feature
            if solver.check([parent_variable, z3.Not(variable)]) == z3.unsat:
                false_optional_features.append(feature.name)

    return false_optional_features
