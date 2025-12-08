import logging
from typing import Any, cast, Optional

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Operation
from flamapy.metamodels.z3_metamodel.models import Z3Model 
from flamapy.metamodels.fm_metamodel.models import FeatureType 

LOGGER = logging.getLogger(__name__)


MAX_ANALYSIS_LENGTH_BOUND = 20  # Limit to 20 characters for String length analysis


class Z3VariableBounds(Operation):
    """Computes the effective bounds (min/max) for numeric features, 
    and the length bounds (min_len/max_len) for string features, with safety checks.
    """

    def __init__(self) -> None:
        self._result: dict[str, Any] = {}
        self._variable_name: Optional[str] = None

    def set_variable_name(self, variable_name: str) -> None:
        """Sets the name of the variable (Feature) to analyze."""
        self._variable_name = variable_name
        
    def get_result(self) -> dict[str, Any]:
        """Returns a dictionary with the found bounds."""
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3VariableBounds':
        if self._variable_name is None:
            raise ValueError("Variable name must be set before execution.")
            
        z3_model = cast(Z3Model, model)
        self._result = variable_bounds_logic(z3_model, self._variable_name)
        return self


def _get_value_from_z3_model(m: z3.ModelRef, var: z3.ExprRef, ftype: FeatureType) -> float | int:
    """Extracts the value of a Z3 expression in model m and converts it to a Python type."""
    val = m.evaluate(var, model_completion=True)
    
    if ftype == FeatureType.INTEGER:
        if z3.is_int_value(val):
            return val.as_long()
        return int(str(val))

    elif ftype == FeatureType.REAL:
        if z3.is_rational_value(val) or z3.is_algebraic_value(val):
            precision = Z3Model.DEFAULT_PRECISION
            return float(val.as_decimal(precision).rstrip('?')) 
        return float(str(val))
    
    raise TypeError(f"Variable type {ftype} not numeric.")


def _find_bounds(model: Z3Model, 
                 var: z3.ExprRef, 
                 ftype: FeatureType) -> tuple[float | str, float | str]:
    """Determine the lower and upper bound (min/max) of a Z3 NUMERIC variable,
    handling unlimited cases (+/- Infinity) and UNSAT.
    """
    solver_check = z3.Solver(ctx=model.ctx)
    solver_check.add(model.constraints)
    if solver_check.check() == z3.unsat:
        return "UNSAT", "UNSAT"

    # Lower Bound (Minimization)
    opt_min = z3.Optimize(ctx=model.ctx)
    opt_min.add(model.constraints)
    opt_min.minimize(var)
    
    min_bound: float | str = "ERROR"
    if opt_min.check() == z3.sat:
        min_val_candidate = _get_value_from_z3_model(opt_min.model(), var, ftype)
        
        # Test: Is there a value less than the candidate, subject to the constraints?
        test_solver = z3.Solver(ctx=model.ctx)
        test_solver.add(model.constraints)
        test_solver.add(var < min_val_candidate)
        
        if test_solver.check() == z3.sat:
            min_bound = float('-inf') 
        else:
            min_bound = min_val_candidate
    
    # Upper Bound (Maximization) ---
    opt_max = z3.Optimize(ctx=model.ctx)
    opt_max.add(model.constraints)
    opt_max.maximize(var)

    max_bound: float | str = "ERROR"
    if opt_max.check() == z3.sat:
        max_val_candidate = _get_value_from_z3_model(opt_max.model(), var, ftype)

        # Test: Is there a value greater than the candidate, subject to the constraints?
        test_solver = z3.Solver(ctx=model.ctx)
        test_solver.add(model.constraints)
        test_solver.add(var > max_val_candidate)
        
        if test_solver.check() == z3.sat:
            max_bound = float('inf')
        else:
            max_bound = max_val_candidate
        
    return min_bound, max_bound


def _find_string_length_bounds_safe(model: Z3Model, 
                                    str_var: z3.ExprRef) -> tuple[float | str, float | str, bool]:
    """Determine the length bounds of a STRING variable, applying a search limit for maximization.
    Returns (min_len, max_len_reported, was_capped).
    """
    len_var = z3.Length(str_var)
    was_capped = False
    
    # 1. Search for Minimum (Similar to _find_bounds, the minimum length is >= 0)
    opt_min = z3.Optimize(ctx=model.ctx)
    opt_min.add(model.constraints)
    opt_min.minimize(len_var)
    
    min_bound: float | str = "ERROR"
    if opt_min.check() == z3.sat:
        # The actual minimum length should always be >= 0
        min_bound = max(0, _get_value_from_z3_model(opt_min.model(), len_var, FeatureType.INTEGER))
    else:
        return "UNSAT", "UNSAT", False
        
    # 2. Search for Maximum (APPLYING THE ANALYSIS LIMIT)
    opt_max = z3.Optimize(ctx=model.ctx)
    opt_max.add(model.constraints)
    
    # Restriction: Bound the search to avoid infinite or very slow search
    opt_max.add(len_var <= MAX_ANALYSIS_LENGTH_BOUND)
    opt_max.maximize(len_var)
    
    max_bound: float | str = "ERROR"
    
    if opt_max.check() == z3.sat:
        max_val_candidate = _get_value_from_z3_model(opt_max.model(), len_var, FeatureType.INTEGER)

        # UNBOUNDED TEST: Check if the *original* model allows going beyond the limit
        test_unbounded_solver = z3.Solver(ctx=model.ctx)
        test_unbounded_solver.add(model.constraints)
        test_unbounded_solver.add(len_var > MAX_ANALYSIS_LENGTH_BOUND)
        
        if test_unbounded_solver.check() == z3.sat:
            # If it allows a length greater than the cap, report as unbounded/out of reach.
            max_bound = float('inf')
            was_capped = True
        else:
            # The actual maximum is at or below the cap
            max_bound = max_val_candidate
            # If the maximum found matches the cap, it means the search hit the cap.
            if max_bound == MAX_ANALYSIS_LENGTH_BOUND:
                 was_capped = True
        
    return min_bound, max_bound, was_capped


def variable_bounds_logic(model: Z3Model, variable_name: str) -> dict[str, Any]:
    """Main logic to compute bounds and domain."""

    if variable_name not in model.features:
        return {'error': f"Feature '{variable_name}' not found in the model."}

    feature_info = model.features[variable_name]
    var_expr = feature_info.val
    ftype = feature_info.ftype

    if var_expr is None or ftype == FeatureType.BOOLEAN:
        return {'error': "Operation not applicable to numeric or string features."}

    if ftype in (FeatureType.INTEGER, FeatureType.REAL):
        min_bound, max_bound = _find_bounds(model, var_expr, ftype)
        is_bounded = not (min_bound == float('-inf') or max_bound == float('inf'))
        return {
            'variable_name': variable_name,
            'feature_type': ftype.name,
            'min_bound': min_bound,
            'max_bound': max_bound,
            'is_bounded': is_bounded,
            'analysis_notes': 'Bounds mathematically verified.'
        }

    elif ftype == FeatureType.STRING:
        min_len, max_len_reported, was_capped = _find_string_length_bounds_safe(model, var_expr)
        
        is_satisfiable = min_len != 'UNSAT'
        is_length_unbounded_model = max_len_reported == float('inf')
        
        analysis_notes = f'Length analysis capped at {MAX_ANALYSIS_LENGTH_BOUND}.'
        if is_length_unbounded_model:
            analysis_notes = 'WARNING: Length is UNBOUNDED or exceeds the cap.' \
                             ' Max length is reported as infinity.'
        elif was_capped:
             analysis_notes = f'WARNING: The true maximum length might be > ' \
                              f'{MAX_ANALYSIS_LENGTH_BOUND}. Reported max is the cap.'
            
        return {
            'variable_name': variable_name,
            'feature_type': ftype.name,
            'is_satisfiable': is_satisfiable,
            'is_length_unbounded': is_length_unbounded_model,
            'min_length': min_len if is_satisfiable else 'UNSAT',
            # If it is unbounded, report 'UNBOUNDED' for readability
            'max_length': max_len_reported if is_satisfiable and not is_length_unbounded_model 
            else 'UNBOUNDED / CAPPED',
            'length_analysis_cap': MAX_ANALYSIS_LENGTH_BOUND,
            'analysis_notes': analysis_notes
        }
    return {'error': "Unknown feature type."}
