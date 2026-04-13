import pathlib
import statistics
import csv
from utils.timer import Timer
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.pysat_metamodel.transformations import FmToPysat
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3CoreFeatures,
    Z3DeadFeatures,
    Z3FalseOptionalFeatures,
)
from flamapy.metamodels.pysat_metamodel.operations import (
    PySATSatisfiable,
    PySATCoreFeatures,
    PySATDeadFeatures,
    PySATFalseOptionalFeatures,
)


HEADER = ['Model', 'Features', 'NonBooleanFeatures', 'Attributes', 'Variables', 'Constraints', 'Solver', 'Operation', 'Tactics', 'Runs', 'Result', 'MeanTime(s)', 'MedianTime(s)', 'StdDevTime(s)']
RUNS = 10
PRECISION = 4

BASE_URL = 'resources/models/generated/pizzas/'
MODEL = 'resources/models/generated/Pizza_z3_extended500b.uvl'
MODELS = ['Pizza_z3_original.uvl',
          'Pizza_z3_extended50.uvl',
          'Pizza_z3_extended100.uvl',
          'Pizza_z3_extended100b.uvl',
          'Pizza_z3_extended200.uvl',
          'Pizza_z3_extended200b.uvl',
          'Pizza_z3_extended500.uvl',
          'Pizza_z3_extended500b.uvl']
SOLVER = 'SAT'
#OPERATIONS = [Z3Satisfiable, Z3CoreFeatures, Z3DeadFeatures, Z3FalseOptionalFeatures]
OPERATIONS = [PySATSatisfiable, PySATCoreFeatures, PySATDeadFeatures, PySATFalseOptionalFeatures]
Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'elim-uncnstr', 'smt']  # tactic 1
#Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'purify-arith', 'tseitin-cnf', 'bit-blast', 'lia2pb', 'fpa2bv', 'smt']  # tactic 1


def execute_operation(model, operation, runs=RUNS):
    times = []
    for i in range(runs):
        print(f'  Run {i+1}/{runs} for operation {operation.__name__}...')
        if SOLVER == 'Z3':
            solver = model.get_solver()
            with Timer(logger=None) as timer:
                value = operation().execute_solver(model, solver).get_result()
        else:
            with Timer(logger=None) as timer:
                value = operation().execute(model).get_result()
        value_num = value if isinstance(value, (bool, int)) else len(value)
        times.append(timer.elapsed_time)
    if times:
        mean_time = round(statistics.mean(times), PRECISION)
        median_time = round(statistics.median(times), PRECISION)
        stddev_time = round(statistics.stdev(times), PRECISION) if len(times) > 1 else 0.0
    else:
        mean_time = median_time = stddev_time = 0.0   
    results = {}
    results['Result'] = value_num
    results['MeanTime(s)'] = mean_time
    results['MedianTime(s)'] = median_time
    results['StdDevTime(s)'] = stddev_time
    return results

def main(model_path):
    model_name = pathlib.Path(model_path).stem
    fm_model = UVLReader(model_path).transform()
    if SOLVER == 'Z3':
        solver_model = FmToZ3(fm_model).transform()
        solver_model.set_tactics(Z3_TACTICS)
    elif SOLVER == 'SAT':
         solver_model = FmToPysat(fm_model).transform()
    
    results = {}
    results['Model'] = model_name
    results['Features'] = len(fm_model.get_features())
    results['NonBooleanFeatures'] = len(fm_model.get_numerical_features()) + len(fm_model.get_string_features())
    results['Attributes'] = sum(len(feat.get_attributes()) for feat in fm_model.get_features())
    results['Constraints'] = len(fm_model.get_constraints())
    if SOLVER == 'Z3':
        results['Variables'] = results['Features'] + results['Attributes'] + results['NonBooleanFeatures']
    else:
        results['Variables'] = results['Features']

    csv_filepath = pathlib.Path('evaluation_results.csv')
    file_exists = csv_filepath.exists()
    with csv_filepath.open('a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=HEADER)
        if not file_exists:
            writer.writeheader()
        
        results['Solver'] = SOLVER
        if SOLVER == 'Z3':
            results['Tactics'] = '+'.join(Z3_TACTICS)
        else:
            results['Tactics'] = 'None'
        for operation in OPERATIONS:
            print(f'Executing {operation.__name__} on model {model_name} with solver {SOLVER}...')
            result = execute_operation(solver_model, operation)
            result['Operation'] = operation.__name__
            result['Runs'] = RUNS
            results.update(result)
            writer.writerow(results)
            csvfile.flush()


if __name__ == "__main__":
    for model in MODELS:
        main(BASE_URL + model)
