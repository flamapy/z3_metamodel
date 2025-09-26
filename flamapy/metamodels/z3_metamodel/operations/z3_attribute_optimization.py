from typing import Any, cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.exceptions import FlamaException
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.fm_metamodel.models import Attribute, AttributeType, FeatureType
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.operations.interfaces import (
    AttributeOptimization, 
    OptimizationGoal
)


class Z3AttributeOptimization(AttributeOptimization):
    """This operation returns the configurations that optimize the given numerical attribute(s).
    
    The optimization is based on the sum of the attribute values across all selected features.
    """

    def __init__(self) -> None:
        self._result: list[Configuration] = []
        self._attributes: dict[Attribute, OptimizationGoal] = {}

    def set_attributes(self, attributes: dict[Attribute, OptimizationGoal]) -> None:
        if any(attr.attribute_type not in [AttributeType.INTEGER, AttributeType.REAL] 
               for attr in attributes):
            raise FlamaException('Only numerical attributes (Integer, Real) can be optimized.')
        self._attributes = attributes

    def optimize(self) -> list[Configuration]:
        return self.get_result()

    def get_result(self) -> list[Configuration]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3AttributeOptimization':
        z3_model = cast(Z3Model, model)
        self._result = optimize(z3_model, self._attributes)
        return self


def optimize(model: Z3Model, attributes: dict[Attribute, OptimizationGoal]) -> list[Configuration]:
    solver_op = z3.Optimize()
    solver_op.add(model.constraints)
    total = sum_attribute(model, list(attributes.keys())[0].name)
    if list(attributes.values())[0] == OptimizationGoal.MINIMIZE:
        solver_op.minimize(total)
    else:
        solver_op.maximize(total)
    configurations = []
    if solver_op.check() == z3.sat:
        m = solver_op.model()
        config_elements = {}
        for feature, feature_info in model.features.items():
            selected = m.evaluate(feature_info.sel, model_completion=True)
            if feature_info.ftype == FeatureType.BOOLEAN:  # boolean feature
                value = z3.is_true(selected)
            else:  # typed feature
                if z3.is_true(selected):
                    value = m.evaluate(feature_info.val, model_completion=True)
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
    return configurations


def sum_attribute(model: Z3Model, attr_name: str) -> z3.ArithRef:
    """Return a Z3 expression representing the sum of the given attribute across all features.
    
    TODO: Consider Integer features as the multiplication of the attributes.
    """
    exprs = []
    for _, feature_info in model.features.items():
        attr = feature_info.attributes.get(attr_name)
        if attr is not None:  # only consider features with the attribute
            value_non_selected = z3.RealVal(0.0)
            if attr['type'] == AttributeType.INTEGER:
                value_non_selected = z3.IntVal(0)
            expr = z3.If(feature_info.sel, attr["var"], value_non_selected)
            exprs.append(expr)
    return z3.Sum(exprs)