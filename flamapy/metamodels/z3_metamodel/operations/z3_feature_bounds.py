import logging
from typing import Any, cast, Optional

import z3

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Operation
from flamapy.metamodels.z3_metamodel.models import Z3Model 
from flamapy.metamodels.fm_metamodel.models import FeatureType 


LOGGER = logging.getLogger(__name__)


MAX_ANALYSIS_LENGTH_BOUND = 20  # Limit to 20 characters for String length analysis


class Z3FeatureBounds(Operation):
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

    def execute(self, model: VariabilityModel) -> 'Z3FeatureBounds':
        if self._variable_name is None:
            raise ValueError("Variable name must be set before execution.")
            
        z3_model = cast(Z3Model, model)
        self._result = variable_bounds_logic(z3_model, self._variable_name)
        return self


def _get_value_from_z3_model(m: z3.ModelRef, var: z3.ExprRef, ftype: FeatureType) -> float | int:
    """Extrae el valor de una expresión Z3 y lo convierte a tipo Python."""
    val = m.evaluate(var, model_completion=True)
    
    if ftype == FeatureType.INTEGER:
        if z3.is_int_value(val):
            return val.as_long()
        return int(str(val))

    elif ftype == FeatureType.REAL:
        # Usa is_rational_value para la verificación de valores reales/racionales
        if z3.is_rational_value(val) or z3.is_algebraic_number(val):
            precision = getattr(Z3Model, 'DEFAULT_PRECISION', 6)
            return float(val.as_decimal(precision).rstrip('?')) 
        return float(str(val))
    
    raise TypeError(f"Variable type {ftype} not numeric.")


def _find_bounds(model: Z3Model, var: z3.ExprRef, ftype: FeatureType) -> tuple[float | str, float | str]:
    """Determina los límites min/max de una variable Z3 NUMÉRICA."""
    solver_check = z3.Solver(ctx=model.ctx)
    solver_check.add(model.constraints)
    if solver_check.check() == z3.unsat:
        return "UNSAT", "UNSAT"

    # Minimización (min_bound)
    opt_min = z3.Optimize(ctx=model.ctx)
    opt_min.add(model.constraints)
    opt_min.minimize(var)
    min_bound: float | str = "ERROR"
    if opt_min.check() == z3.sat:
        min_val_candidate = _get_value_from_z3_model(opt_min.model(), var, ftype)
        test_solver = z3.Solver(ctx=model.ctx)
        test_solver.add(model.constraints)
        test_solver.add(var < min_val_candidate)
        if test_solver.check() == z3.sat:
            min_bound = float('-inf') 
        else:
            min_bound = min_val_candidate
    
    # Maximización (max_bound)
    opt_max = z3.Optimize(ctx=model.ctx)
    opt_max.add(model.constraints)
    opt_max.maximize(var)
    max_bound: float | str = "ERROR"
    if opt_max.check() == z3.sat:
        max_val_candidate = _get_value_from_z3_model(opt_max.model(), var, ftype)
        test_solver = z3.Solver(ctx=model.ctx)
        test_solver.add(model.constraints)
        test_solver.add(var > max_val_candidate)
        if test_solver.check() == z3.sat:
            max_bound = float('inf')
        else:
            max_bound = max_val_candidate
        
    return min_bound, max_bound


def _find_string_length_bounds_safe(model: Z3Model, str_var: z3.ExprRef) -> tuple[float | str, float | str, bool]:
    """
    Determina los límites de longitud de STRING con chequeo de seguridad.
    Retorna (min_len, max_len_reportado, was_capped).
    """
    len_var = z3.Length(str_var)
    was_capped = False
    
    # Búsqueda del Mínimo
    opt_min = z3.Optimize(ctx=model.ctx)
    opt_min.add(model.constraints)
    opt_min.minimize(len_var)
    min_bound: float | str = "ERROR"
    if opt_min.check() == z3.sat:
        min_bound = max(0, _get_value_from_z3_model(opt_min.model(), len_var, FeatureType.INTEGER))
    else:
        return "UNSAT", "UNSAT", False
        
    # Búsqueda del Máximo (APLICANDO EL LÍMITE)
    opt_max = z3.Optimize(ctx=model.ctx)
    opt_max.add(model.constraints)
    opt_max.add(len_var <= MAX_ANALYSIS_LENGTH_BOUND) # Restricción de seguridad
    opt_max.maximize(len_var)
    
    max_bound: float | str = "ERROR"
    
    if opt_max.check() == z3.sat:
        max_val_candidate = _get_value_from_z3_model(opt_max.model(), len_var, FeatureType.INTEGER)

        # PRUEBA DE ILIMITACIÓN: ¿Permite el modelo una longitud mayor al límite?
        test_unbounded_solver = z3.Solver(ctx=model.ctx)
        test_unbounded_solver.add(model.constraints)
        test_unbounded_solver.add(len_var > MAX_ANALYSIS_LENGTH_BOUND)
        
        if test_unbounded_solver.check() == z3.sat:
            max_bound = float('inf')
            was_capped = True
        else:
            max_bound = max_val_candidate
            if max_bound == MAX_ANALYSIS_LENGTH_BOUND:
                 was_capped = True
        
    return min_bound, max_bound, was_capped


def variable_bounds_logic(model: Z3Model, variable_name: str) -> dict[str, Any]:
    """
    Lógica principal unificada para computar límites.
    Salida: {'min': Any, 'max': Any, 'bounded': bool}
    """
    if variable_name not in model.features:
        return {'error': f"Feature '{variable_name}' not found."}

    feature_info = model.features[variable_name]
    var_expr = feature_info.val
    ftype = feature_info.ftype

    if var_expr is None or ftype == FeatureType.BOOLEAN:
        return {'error': "Operation not applicable to this feature type."}

    final_min: Any = 'N/A'
    final_max: Any = 'N/A'
    is_bounded: bool = False

    # 1. Lógica para NUMÉRICOS (INTEGER/REAL)
    if ftype in (FeatureType.INTEGER, FeatureType.REAL):
        min_b, max_b = _find_bounds(model, var_expr, ftype)
        
        final_min = min_b
        final_max = max_b
        
        if min_b == 'UNSAT' or max_b == 'UNSAT':
            is_bounded = False
        else:
            is_bounded = not (min_b == float('-inf') or max_b == float('inf'))

    # 2. Lógica para STRINGS (basada en longitud)
    elif ftype == FeatureType.STRING:
        min_len, max_len, was_capped = _find_string_length_bounds_safe(model, var_expr)
        
        if min_len == 'UNSAT':
            final_min = 'UNSAT'
            final_max = 'UNSAT'
            is_bounded = False
        else:
            final_min = min_len # Mínimo de la longitud
            
            is_length_unbounded_model = max_len == float('inf')

            if is_length_unbounded_model:
                final_max = float('inf')
                is_bounded = False
            elif was_capped:
                # Si se alcanzó el tope de seguridad, la acotación real es incierta.
                final_max = f'CAPPED ({MAX_ANALYSIS_LENGTH_BOUND})'
                is_bounded = False
            else:
                final_max = max_len # Máximo de la longitud
                is_bounded = True
    
    # Formato de salida unificado
    return {
        'variable_name': variable_name,
        'feature_type': ftype.name,
        'min': final_min,
        'max': final_max,
        'bounded': is_bounded,
    }