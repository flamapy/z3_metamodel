from typing import cast, Any

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
    expr = Z3Model.sum_attribute(z3_model, attribute)
    solver_opt = z3.Optimize(ctx=z3_model.ctx)
    solver_opt.add(z3_model.constraints)

    if goal == OptimizationGoal.MINIMIZE:
        _ = solver_opt.minimize(expr)
    else:
        _ = solver_opt.maximize(expr)
        
    if solver_opt.check() != z3.sat:
        return []

    # 1. Obtener el modelo óptimo (la primera solución)
    m_opt = solver_opt.model()
    
    # 2. Calcular el valor óptimo preciso en Z3 y su equivalente Python
    opt_val_z3 = m_opt.evaluate(expr, model_completion=True)
    opt_val_py = _z3_to_number(opt_val_z3) # ¡Usando opt_val_py aquí!

    # 3. Inicializar el solucionador para enumerar TODAS las soluciones
    solver_enum = z3.Solver(ctx=z3_model.ctx)
    solver_enum.add(z3_model.constraints)

    # Se usa opt_val_z3 para la restricción de igualdad dentro de Z3 para máxima precisión.
    solver_enum.add(expr == opt_val_z3)

    results: list[tuple[Configuration, dict[str, int | float]]] = []
    
    # 4. Bucle para enumerar todas las configuraciones con el valor óptimo
    while solver_enum.check() == z3.sat:
        m = solver_enum.model()
        
        # Usamos el valor Python óptimo ya calculado (opt_val_py) para el resultado. 
        # Sabemos que 'val' debe ser igual a 'opt_val_py' debido a la restricción añadida.
        val = opt_val_py

        config, block = extract_configuration(z3_model, m)
        # Aquí se usa el valor óptimo Python
        results.append((config, {attribute: val})) 
        
        # Bloquear la configuración actual para forzar una diferente
        solver_enum.add(z3.Or(block)) 

    return results


def optimize_multi_objective(z3_model: Z3Model,
                             attributes: dict[str, 'OptimizationGoal']
                             ) -> list[tuple['Configuration', dict[str, int | float]]]:
    """
    Busca el Frente de Pareto de soluciones no-dominadas usando un algoritmo de bloqueo iterativo.
    """
    # (nombre_attr, expr_z3, meta)
    objectives = [(attr, Z3Model.sum_attribute(z3_model, attr), goal)
                  for attr, goal in attributes.items()]

    pareto_solutions: list[tuple[Any, dict[str, int | float]]] = [] # Almacena candidatos a Pareto

    solver = z3.Solver(ctx=z3_model.ctx)
    solver.add(z3_model.constraints)

    # Definir una pequeña tolerancia para comparaciones de números reales en Z3
    EPSILON = z3.RealVal('0.000001', ctx=z3_model.ctx) # 1e-6
    epsilon_py = 1e-6 # Tolerancia para el filtro de Python

    # Bucle para encontrar soluciones no-dominadas (candidatos a Pareto)
    while solver.check() == z3.sat:
        m = solver.model()
        
        # 1. Obtener los valores de objetivo de la nueva solución encontrada
        attr_values = {name: _z3_to_number(m.evaluate(expr, model_completion=True))
                       for name, expr, _ in objectives}

        config, block = extract_configuration(z3_model, m)
        
        # 2. Almacenar la nueva solución candidata
        pareto_solutions.append((config, attr_values))

        # 3. Definir la restricción de No-Dominancia para la próxima iteración
        non_dominance_constraints = []
        
        # El Solver debe encontrar una solución X que NO sea dominada por ninguna solución P ya encontrada.
        for p_config, p_values in pareto_solutions:
            
            # X debe ser estrictamente mejor que P en AL MENOS UN objetivo (con tolerancia)
            at_least_one_better = [] 
            
            for name, expr, goal in objectives:
                p_val = p_values[name]
                
                if isinstance(p_val, float):
                    p_val_z3 = z3.RealVal(str(p_val), ctx=z3_model.ctx)

                    if goal == OptimizationGoal.MINIMIZE:
                        # Queremos expr < p_val_z3. Usamos tolerancia: expr <= p_val_z3 - EPSILON
                        at_least_one_better.append(expr <= p_val_z3 - EPSILON) 
                    else: # MAXIMIZE
                        # Queremos expr > p_val_z3. Usamos tolerancia: expr >= p_val_z3 + EPSILON
                        at_least_one_better.append(expr >= p_val_z3 + EPSILON) 
                else: # INTEGER
                    p_val_z3 = z3.IntVal(p_val, ctx=z3_model.ctx) 
                    
                    if goal == OptimizationGoal.MINIMIZE:
                        at_least_one_better.append(expr < p_val_z3) 
                    else: # MAXIMIZE
                        at_least_one_better.append(expr > p_val_z3) 

            # Restricción: La próxima solución X DEBE satisfacer z3.Or(at_least_one_better) respecto a P.
            non_dominance_constraints.append(z3.Or(at_least_one_better))

        # 4. Aplicar las restricciones al Solver
        solver.add(z3.And(non_dominance_constraints))

        # 5. Bloqueo de la configuración actual (para forzar una configuración diferente)
        solver.add(z3.Or(block)) 


    # ================================================================
    # FILTRADO FINAL DE DOMINANCIA Y UNICIDAD (Red de Seguridad)
    # ================================================================

    final_pareto_front: list[tuple[Any, dict[str, int | float]]] = []

    # A. Filtrado de Dominancia: Eliminar soluciones que fueron dominadas
    for i in range(len(pareto_solutions)):
        config_i, values_i = pareto_solutions[i]
        is_dominated_by_another = False

        for j in range(len(pareto_solutions)):
            if i == j:
                continue
            
            config_j, values_j = pareto_solutions[j]
            
            # Verificar si la solución j DOMINA a la solución i
            if is_dominated(values_i, values_j, attributes, epsilon=epsilon_py):
                is_dominated_by_another = True
                break
                
        if not is_dominated_by_another:
            final_pareto_front.append((config_i, values_i))

    # B. Filtrado de Unicidad (por valores de objetivo)
    # Esto elimina múltiples configuraciones que tienen el MISMO par de valores óptimos.
    unique_solutions: dict[tuple[int | float, ...], tuple[Any, dict[str, int | float]]] = {}
    
    for config, values in final_pareto_front:
        key = tuple(round(v, 6) if isinstance(v, float) else v for v in values.values())
        if key not in unique_solutions:
            unique_solutions[key] = (config, values)

    return list(unique_solutions.values())


def _z3_to_number(val: z3.ExprRef) -> int | float:
    """Convert Z3 numeric value to Python float or int safely."""
    if hasattr(val, "as_decimal"):
        return float(val.as_decimal(20).rstrip('?'))
    elif hasattr(val, "as_long"):
        return val.as_long()
    elif hasattr(val, "numeral_as_long"):
        return val.numeral_as_long()
    else:
        return float(val.as_string())


def extract_configuration(z3_model: Z3Model, 
                          solution_model: z3.ModelRef
                          ) -> tuple[Configuration, list[z3.ExprRef]]:
    """
    Extract a configuration (feature -> value) and its blocking clause.
    """
    config_elements = {}
    block = []

    for feature, feature_info in z3_model.features.items():
        sel = feature_info.sel
        selected = solution_model.evaluate(sel, model_completion=True)
        block.append(sel != selected)

        if feature_info.ftype == FeatureType.BOOLEAN:
            value = z3.is_true(selected)
        else:
            if z3.is_true(selected):
                val_expr = feature_info.val
                if val_expr is None:
                    raise ValueError(f'Feature {feature} has no value expression.')
                val_expr = feature_info.val
                value = solution_model.evaluate(val_expr, model_completion=True)
                block.append(val_expr != value)

                if feature_info.ftype == FeatureType.INTEGER:
                    value = value.as_long()
                elif feature_info.ftype == FeatureType.REAL:
                    # **CORRECCIÓN CRÍTICA:** Usar alta precisión (ej. 20) al evaluar Real.
                    # El valor Python debe ser exacto para el bloqueo.
                    value = float(value.as_decimal(20).rstrip('?')) 
                elif feature_info.ftype == FeatureType.STRING:
                    value = value.as_string()
            else:
                value = False

        config_elements[feature] = value

    return Configuration(config_elements), block


def is_dominated(values_i: dict[str, Any], 
                 values_j: dict[str, Any], 
                 attributes: dict[str, OptimizationGoal],
                 epsilon: float = 1e-6) -> bool:
    """
    Verifica si la solución 'i' es dominada por la solución 'j'.
    
    j domina a i si:
    1. j es mejor o igual a i en TODOS los objetivos.
    2. j es ESTRICTAMENTE mejor que i en AL MENOS UN objetivo (considerando epsilon).
    """
    is_better_in_at_least_one = False
    is_worse_in_any = False
    
    for attr, goal in attributes.items():
        val_i = values_i[attr]
        val_j = values_j[attr]
        
        if goal == OptimizationGoal.MAXIMIZE:
            # i es PEOR que j si val_i < val_j
            # j es MEJOR que i si val_j > val_i
            
            # Condición de dominancia: j debe ser >= i en todos.
            if val_j < val_i - epsilon: # j es PEOR que i (val_j < val_i)
                is_worse_in_any = True
                break 
            
            # Condición de dominancia: j debe ser > i en al menos uno.
            if val_j > val_i + epsilon: # j es ESTRICTAMENTE MEJOR que i
                is_better_in_at_least_one = True
                
        elif goal == OptimizationGoal.MINIMIZE:
            # i es PEOR que j si val_i > val_j
            # j es MEJOR que i si val_j < val_i
            
            # Condición de dominancia: j debe ser <= i en todos.
            if val_j > val_i + epsilon: # j es PEOR que i (val_j > val_i)
                is_worse_in_any = True
                break
            
            # Condición de dominancia: j debe ser < i en al menos uno.
            if val_j < val_i - epsilon: # j es ESTRICTAMENTE MEJOR que i
                is_better_in_at_least_one = True
                
    # Si j no fue peor que i en ningún objetivo Y fue estrictamente mejor en al menos uno, entonces j domina a i.
    return not is_worse_in_any and is_better_in_at_least_one