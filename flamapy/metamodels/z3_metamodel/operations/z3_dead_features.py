from typing import Any, cast

from flamapy.core.models import VariabilityModel
from flamapy.core.operations import DeadFeatures
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.operations import Z3Backbone


class Z3DeadFeatures(DeadFeatures):

    def __init__(self) -> None:
        self._result: list[Any] = []

    def get_dead_features(self) -> list[Any]:
        return self.get_result()

    def get_result(self) -> list[Any]:
        return self._result

    def execute(self, model: VariabilityModel) -> 'Z3DeadFeatures':
        z3_model = cast(Z3Model, model)
        self._result = Z3Backbone().execute(z3_model).get_result()["dead"]
        return self
