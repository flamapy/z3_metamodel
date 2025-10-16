from typing import cast

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.exceptions import FlamaException
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.fm_metamodel.models import AttributeType, FeatureType
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
        self._attributes: dict[str, OptimizationGoal] = {}

    def set_attributes(self, attributes: dict[str, OptimizationGoal]) -> None:
        if not attributes:
            raise FlamaException("At least one attribute must be provided for optimization.")
        self._attributes = attributes

    def optimize(self) -> list[Configuration]:
        return self.get_result()

    def get_result(self) -> list[Configuration]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3AttributeOptimization':
        z3_model = cast(Z3Model, model)
        # Validate attributes
        for attr_name in self._attributes:
            if attr_name not in z3_model.attributes_types:
                raise FlamaException(f'Attribute "{attr_name}" not found in the model.')
            attr_type = z3_model.attributes_types[attr_name]
            if attr_type not in [AttributeType.INTEGER, AttributeType.REAL]:
                raise FlamaException(f'Only numerical attributes (Integer, Real) can be optimized.'
                                     f' Attribute "{attr_name}" is of type {attr_type}.')
        self._result = optimize_pareto(z3_model, self._attributes)
        return self


def optimize_pareto(z3_model: Z3Model, 
                    attributes: dict[str, OptimizationGoal]
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
                              attribute: str,
                              goal: OptimizationGoal
                              ) -> list[tuple[Configuration, dict[str, int | float]]]:
    context = z3.Context()
    expr = sum_attribute(z3_model, attribute).translate(context)
    solver_opt = z3.Optimize(ctx=context)
    solver_opt.add([c.translate(context) for c in z3_model.constraints])

    if goal == OptimizationGoal.MINIMIZE:
        handle = solver_opt.minimize(expr)
    else:
        handle = solver_opt.maximize(expr)
    if solver_opt.check() != z3.sat:
        return []

    if goal == OptimizationGoal.MINIMIZE:
        opt_val = solver_opt.lower(handle)
    else:
        opt_val = solver_opt.upper(handle)
    if opt_val is None:
        return []

    # Enumerate all configurations with expr == opt_val
    solver_enum = z3.Solver(ctx=context)
    solver_enum.add([c.translate(context) for c in z3_model.constraints])
    solver_enum.add(expr == opt_val)

    results: list[tuple[Configuration, dict[str, int | float]]] = []
    while solver_enum.check() == z3.sat:
        m = solver_enum.model()
        val = _z3_to_number(m.evaluate(expr, model_completion=True))
        config, block = extract_configuration(z3_model, m, context)
        results.append((config, {attribute: val}))
        solver_enum.add(z3.Or(block))

    return results


def optimize_multi_objective(z3_model: Z3Model,
                             attributes: dict[str, OptimizationGoal]
                             ) -> list[tuple[Configuration, dict[str, int | float]]]:
    context = z3.Context()

    # Convert expressions to the new context
    objectives = [(attr, sum_attribute(z3_model, attr).translate(context), goal)
                  for attr, goal in attributes.items()]

    pareto_solutions: list[tuple[Configuration, dict[str, int | float]]] = []

    solver = z3.Optimize(ctx=context)
    solver.add([c.translate(context) for c in z3_model.constraints])

    while solver.check() == z3.sat:
        m = solver.model()
        attr_values = {name: _z3_to_number(m.evaluate(expr, model_completion=True))
                       for name, expr, _ in objectives}

        config, _ = extract_configuration(z3_model, m, context)
        pareto_solutions.append((config, attr_values))

        # Proper Pareto dominance blocking
        dominance_constraints = []
        for _, expr, goal in objectives:
            val = m.evaluate(expr, model_completion=True)
            if goal == OptimizationGoal.MINIMIZE:
                dominance_constraints.append(expr < val)
            else:
                dominance_constraints.append(expr > val)
        solver.add(z3.Or(dominance_constraints))

    return pareto_solutions


def _z3_to_number(val: z3.ExprRef) -> int | float:
    """Convert Z3 numeric value to Python float or int safely."""
    if hasattr(val, "as_decimal"):
        return float(val.as_decimal(10).rstrip('?'))
    elif hasattr(val, "as_long"):
        return val.as_long()
    elif hasattr(val, "numeral_as_long"):
        return val.numeral_as_long()
    else:
        return float(val.as_string())


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
                          solution_model: z3.ModelRef,
                          context: z3.Context | None = None
                          ) -> tuple[Configuration, list[z3.ExprRef]]:
    """
    Extract a configuration (feature -> value) and its blocking clause.

    If context is provided, all expressions are translated to that context.
    """
    config_elements = {}
    block = []

    for feature, feature_info in z3_model.features.items():
        sel = feature_info.sel.translate(context) if context else feature_info.sel
        selected = solution_model.evaluate(sel, model_completion=True)
        block.append(sel != selected)

        if feature_info.ftype == FeatureType.BOOLEAN:
            value = z3.is_true(selected)
        else:
            if z3.is_true(selected):
                val_expr = feature_info.val
                if val_expr is None:
                    raise ValueError(f'Feature {feature} has no value expression.')
                val_expr = val_expr.translate(context) if context else feature_info.val
                value = solution_model.evaluate(val_expr, model_completion=True)
                block.append(val_expr != value)

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
