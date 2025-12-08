import logging
from typing import Any, cast

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import Operation
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.operations import Z3FeatureBounds
from flamapy.metamodels.fm_metamodel.models import FeatureType


LOGGER = logging.getLogger(__name__)


class Z3AllFeatureBounds(Operation):
    """Computes the effective bounds (min/max) for ALL typed feature 
    (Integer, Real, String length) in the Z3 model.
    """

    def __init__(self) -> None:
        # El resultado será un diccionario donde la clave es el nombre de la variable
        # y el valor es el diccionario de bounds (min, max, bounded).
        self._result: dict[str, dict[str, Any]] = {}

    def get_result(self) -> dict[str, dict[str, Any]]:
        """
        Devuelve un diccionario con los bounds de todas las variables tipadas.
        Formato: {'var_name': {'min': ..., 'max': ..., 'bounded': True/False}, ...}
        """
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3AllFeatureBounds':
        z3_model = cast(Z3Model, model)
        all_bounds_result: dict[str, dict[str, Any]] = {}
        
        # Instanciamos la operación de bajo nivel que ya definiste
        bounds_op = Z3FeatureBounds()

        # Iterar sobre todas las features del modelo Z3
        for var_name, feature_info in z3_model.features.items():
            ftype = feature_info.ftype
            
            # Solo procesar variables tipadas (Integer, Real, String)
            if ftype in (FeatureType.INTEGER, FeatureType.REAL, FeatureType.STRING):
                
                try:
                    # 1. Configurar la operación con el nombre de la variable
                    bounds_op.set_variable_name(var_name)
                    
                    # 2. Ejecutar la operación Z3VariableBounds para la variable actual
                    bounds_op.execute(z3_model)
                    
                    # 3. Obtener el resultado unificado
                    bounds = bounds_op.get_result()
                    
                    # 4. Almacenar el resultado en el diccionario final
                    if 'error' not in bounds:
                        # Aseguramos que solo guardamos los campos unificados y esenciales
                        all_bounds_result[var_name] = {
                            'feature_type': bounds.get('feature_type', ftype.name),
                            'min': bounds.get('min', 'N/A'),
                            'max': bounds.get('max', 'N/A'),
                            'bounded': bounds.get('bounded', False)
                        }
                    else:
                        LOGGER.warning(f"Error calculating bounds for {var_name}: {bounds['error']}")
                        all_bounds_result[var_name] = {
                            'feature_type': ftype.name,
                            'min': 'ERROR',
                            'max': 'ERROR',
                            'bounded': False
                        }
                        
                except Exception as e:
                    LOGGER.error(f"Execution error for variable {var_name}: {e}")
                    all_bounds_result[var_name] = {
                        'feature_type': ftype.name,
                        'min': 'RUNTIME_ERROR',
                        'max': 'RUNTIME_ERROR',
                        'bounded': False
                    }


        self._result = all_bounds_result
        return self