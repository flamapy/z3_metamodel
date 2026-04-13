from typing import Any, cast, Callable, Optional

from pysat.solvers import Solver

from flamapy.core.operations import Configurations
from flamapy.metamodels.configuration_metamodel.models.configuration import Configuration
from flamapy.metamodels.pysat_metamodel.models.pysat_model import PySATModel
from flamapy.core.models import VariabilityModel


class PySATConfigurationsNumber(Configurations):

    def __init__(self) -> None:
        self.result: int = 0
        self.solver = Solver(name='glucose3')

    def get_configurations(self) -> int:
        return self.get_result()

    def set_progress_reporter(self, report_progress: Callable) -> None:
        self.report_progress = report_progress

    def get_result(self) -> int:
        return self.result

    def execute(self, model: VariabilityModel) -> 'PySATConfigurations':
        sat_model = cast(PySATModel, model)
        self.result = configurations(self.solver, sat_model, self.report_progress)
        return self


def configurations(solver: Solver, model: PySATModel, report_progress: Optional[Callable] = None) -> int:
    for clause in model.get_all_clauses():
        solver.add_clause(clause)

    result = []
    for solutions in solver.enum_models():
        product: dict[Any, bool] = {}
        for variable in solutions:
            if variable > 0:
                product[model.features.get(variable)] = True
        result.append(Configuration(product))
        if report_progress is not None:
            report_progress(len(result))
    solver.delete()
    return len(result)
