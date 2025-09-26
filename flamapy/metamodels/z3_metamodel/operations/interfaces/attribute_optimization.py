from abc import abstractmethod
from enum import Enum

from flamapy.core.operations import Operation
from flamapy.metamodels.configuration_metamodel.models import Configuration
from flamapy.metamodels.fm_metamodel.models import Attribute


class OptimizationGoal(Enum):
    MAXIMIZE = 'Maximize'
    MINIMIZE = 'Minimize'


class AttributeOptimization(Operation):
    """This operation returns the configurations that optimize the given attribute(s)."""

    @abstractmethod
    def __init__(self) -> None:
        pass

    @abstractmethod
    def set_attributes(self, attributes: dict[Attribute, OptimizationGoal]) -> None:
        pass
        
    @abstractmethod
    def optimize(self) -> list[Configuration]:
        pass
