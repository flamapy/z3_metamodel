from typing import Optional, cast

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import ConfigurationsNumber
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.operations import Z3Configurations


class Z3ConfigurationsNumber(ConfigurationsNumber):
    """It computes the number of solutions of the z3 model.

    This method does not scale well for large or infinite domains 
    (e.g., Integer variables without a bounded domain), since it iterates over all solutions.
    """

    def __init__(self) -> None:
        self._result: int = 0
        self._partial_configuration: Optional[Configuration] = None

    def set_partial_configuration(self, partial_configuration: Optional[Configuration]) -> None:
        self._partial_configuration = partial_configuration

    def execute(self, model: VariabilityModel) -> 'Z3ConfigurationsNumber':
        z3_model = cast(Z3Model, model)
        self._result = configurations_number(z3_model, self._partial_configuration)
        return self

    def get_result(self) -> int:
        return self._result

    def get_configurations_number(self) -> int:
        return self.get_result()


def configurations_number(model: Z3Model,
                          partial_configuration: Optional[Configuration] = None) -> int:
    configurations_op = Z3Configurations()
    configurations_op.set_partial_configuration(partial_configuration)
    configurations = configurations_op.execute(model).get_result()
    return len(configurations)
