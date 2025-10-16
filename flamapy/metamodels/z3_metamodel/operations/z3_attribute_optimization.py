from typing import cast

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
        self._result = optimize_pareto(z3_model, self._attributes)
        return self


def optimize_pareto(z3_model: Z3Model, 
                    attributes: dict[Attribute, OptimizationGoal]
                    ) -> list[tuple[Configuration, dict[str, float]]]:
    """
    Unified optimization entry point:
    - If one attribute: return all optimal configurations.
    - If multiple attributes: return Pareto front of non-dominated configurations.
    """
    if not attributes:
        return []

    if len(attributes) == 1:
        (attr, goal), = attributes.items()
        return optimize_single_objective(z3_model, attr, goal)
    else:
        return optimize_multi_objective(z3_model, attributes)
    

def optimize_single_objective(z3_model: Z3Model,
                              attribute: Attribute,
                              goal: OptimizationGoal
                              ) -> list[tuple[Configuration, dict[str, int | float]]]:
    """Return all configurations achieving the optimal value of a single numerical attribute."""
    expr = sum_attribute(z3_model, attribute.name)
    solver_opt = z3.Optimize()
    solver_opt.add(z3_model.constraints)

    if goal == OptimizationGoal.MINIMIZE:
        handle = solver_opt.minimize(expr)
    else:
        handle = solver_opt.maximize(expr)

    if solver_opt.check() != z3.sat:
        return []

    # Get the optimal value
    if goal == OptimizationGoal.MINIMIZE:
        opt_val = solver_opt.lower(handle)
    else:
        opt_val = solver_opt.upper(handle)
    if opt_val is None:
        return []

    # Enumerate all configurations with expr == opt_val
    solver_enum = z3.Solver()
    solver_enum.add(z3_model.constraints)
    solver_enum.add(expr == opt_val)

    results: list[tuple[Configuration, dict[str, int | float]]] = []

    while solver_enum.check() == z3.sat:
        m = solver_enum.model()
        val = m.evaluate(expr, model_completion=True)
        val = _z3_to_number(val)
        config, block = extract_configuration(z3_model, m)
        results.append((config, {attribute.name: val}))
        solver_enum.add(z3.Or(block))

    return results


def optimize_multi_objective(z3_model: Z3Model,
                             attributes: dict[Attribute, OptimizationGoal]
                             ) -> list[tuple[Configuration, dict[str, int | float]]]:
    """Compute the Pareto front of non-dominated configurations."""
    objectives = [(attr.name, sum_attribute(z3_model, attr.name), goal)
                  for attr, goal in attributes.items()]

    pareto_solutions: list[tuple[Configuration, dict[str, int | float]]] = []

    solver = z3.Optimize()
    solver.add(z3_model.constraints)

    while solver.check() == z3.sat:
        m = solver.model()

        # Collect objective values
        attr_values: dict[str, float] = {}
        for name, expr, goal in objectives:
            val = m.evaluate(expr, model_completion=True)
            attr_values[name] = _z3_to_number(val)

        # Extract configuration
        config, _ = extract_configuration(z3_model, m)
        pareto_solutions.append((config, attr_values))

        # Block dominated solutions
        dominance = []
        for _, expr, goal in objectives:
            val = m.evaluate(expr, model_completion=True)
            if goal == OptimizationGoal.MINIMIZE:
                dominance.append(expr < val)
            else:
                dominance.append(expr > val)
        solver.add(z3.Or(dominance))

    return pareto_solutions


def _z3_to_number(val: z3.ExprRef) -> int | float:
    """Convert Z3 numeric value to Python float or int safely."""
    # 1. Manage real values (RealSort) from Z3
    if hasattr(val, "as_decimal"):
        return float(val.as_decimal(10).rstrip('?'))
    # 2. Manage integer values (IntSort) from Z3
    elif hasattr(val, "as_long"):
        return val.as_long()
    # 3. Fallback (for simple or literal values)
    elif hasattr(val, "numeral_as_long"):
        return val.numeral_as_long()
    # Fallback to float if unknown numeric type
    else:
        return float(val.as_string()) # Forced conversion if all else fails


def sum_attribute(model: Z3Model, attr_name: str) -> z3.ArithRef:
    """Return a Z3 expression representing the sum of the given attribute across all features."""
    exprs = []
    for _, feature_info in model.features.items():
        attr = feature_info.attributes.get(attr_name)
        if attr is not None:
            zero_val = z3.IntVal(0) if attr['type'] == AttributeType.INTEGER else z3.RealVal(0.0)
            expr = z3.If(feature_info.sel, attr['var'], zero_val)
            exprs.append(expr)
    return z3.Sum(exprs) if exprs else z3.RealVal(0.0)


def extract_configuration(z3_model: Z3Model, 
                          solution_model: z3.ModelRef
                          ) -> tuple[Configuration, list[z3.ExprRef]]:
    """Extract a configuration (feature -> value) and its blocking clause."""
    config_elements = {}
    block = []

    for feature, feature_info in z3_model.features.items():
        selected = solution_model.evaluate(feature_info.sel, model_completion=True)
        block.append(feature_info.sel != selected)

        if feature_info.ftype == FeatureType.BOOLEAN:
            value = z3.is_true(selected)
        else:
            if z3.is_true(selected):
                value = solution_model.evaluate(feature_info.val, model_completion=True)
                block.append(feature_info.val != value)
                if feature_info.ftype == FeatureType.INTEGER:
                    value = value.as_long()
                elif feature_info.ftype == FeatureType.REAL:
                    value = float(value.as_decimal(6).rstrip('?'))
                elif feature_info.ftype == FeatureType.STRING:
                    value = value.as_string()
            else:
                value = False
        config_elements[feature] = value

    return Configuration(config_elements), block