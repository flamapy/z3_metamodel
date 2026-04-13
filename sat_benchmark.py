import statistics
import argparse
import multiprocessing
from multiprocessing.managers import DictProxy
from pathlib import Path
from typing import Any, Optional, Callable

from flamapy.core.operations import Operation
from flamapy.metamodels.fm_metamodel.transformations import UVLReader, FlatFM
from flamapy.metamodels.fm_metamodel.operations import FMLanguageLevel
from flamapy.metamodels.fm_metamodel.transformations.refactorings import FeatureCardinalityRefactoring
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.pysat_metamodel.transformations import FmToPysat
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
from custom_operations.pysat_configurations_number import PySATConfigurationsNumber
from utils.timer import Timer
from utils.file_manager import get_models_to_run
from utils.benchmark_utils import (
    write_results_incrementally,
    CSV_HEADERS,
    KEY_MODEL_NAME, 
    KEY_OPERATION, 
    KEY_RESULT, 
    KEY_RUNS, 
    KEY_TIME_MEAN, 
    KEY_TIME_MEDIAN, 
    KEY_TIME_STDDEV,
    KEY_TIMEOUT
)


N_RUNS = 10
PRECISION = 4
OUTPUT_CSV = f'sat_benchmark_results.csv'
TIMEOUT = 60
OPERATIONS = {'Satisfiable': PySATSatisfiable, 
              'CoreFeatures': PySATCoreFeatures, 
              'DeadFeatures': PySATDeadFeatures, 
              'FalseOptionalFeatures': PySATFalseOptionalFeatures,
              'ConfigurationsNumber': PySATConfigurationsNumber}
              #'AttributeOptimization': Z3AttributeOptimization}
#Z3_TACTICS = ['simplify', 'smt']
Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'smt']  # tactic 1
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'purify-arith', 'tseitin-cnf', 'bit-blast', 'lia2pb', 'fpa2bv', 'smt']  # tactic 2
# Z3_TACTICS = ['simplify', 'propagate-values', 'smt']  # tactic 3
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'bit-blast', 'smt']   # tactic 4
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'tseitin-cnf', 'smt']   # tactic 5
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'bit-blast', 'tseitin-cnf', 'smt']   # tactic 6
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'purify-arith', 'smt']  # tactic 7
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'bit-blast', 'sat']   # tactic 8
# Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'tseitin-cnf', 'sat']   # tactic 9
#Z3_TACTICS = ['simplify', 'solve-eqs', 'smt'] 
#Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'lia2pb', 'smt'] # tactic 3
#Z3_TACTICS = ['simplify', 'propagate-values', 'solve-eqs', 'bit-blast', 'sat'] # tactic 2


def worker_execute(op_class: Callable, fm_path: str, shared_data: DictProxy) -> None:
    try:
        fm_model = UVLReader(fm_path).transform()
        # Flat the FM
        flat_op = FlatFM(fm_model)
        flat_op.set_maintain_namespaces(False)
        fm_model = flat_op.transform()

        # Refactor feature cardinalities
        #fm_model = FeatureCardinalityRefactoring(fm_model).transform()
    except Exception as e:
        shared_data['status'] = f'ERROR: reading FM model from {fm_path}: {e}'
        return

    try:
        sat_model = FmToPysat(fm_model).transform()
    except Exception as e:
        shared_data['status'] = f'ERROR: transforming FM to SAT model from {fm_path}: {e}'
        return

    op = op_class()
    def report_progress(configurations_number: int) -> None:
        shared_data['partial_result'] = configurations_number
    if op.__class__ == PySATConfigurationsNumber:
        op.set_progress_reporter(report_progress)

    try:
        with Timer(logger=None) as timer:
            op.execute(sat_model)
        result = op.get_result()
        shared_data['final_result'] = result
        shared_data['elapsed_time'] = timer.elapsed_time
        shared_data['status'] = 'COMPLETED'
    except Exception as e:
        shared_data['status'] = f'ERROR: Execution failed for {op.__class__.__name__}: {e}'


def analyze_model(fm_path: str,
                  operations: list[Callable],
                  n_runs: int = N_RUNS) -> None:
    model_name = Path(fm_path).stem
    fm_model = UVLReader(fm_path).transform()
    # Flat the FM
    flat_op = FlatFM(fm_model)
    flat_op.set_maintain_namespaces(False)
    fm_model = flat_op.transform()

    # Refactor feature cardinalities
    #fm_model = FeatureCardinalityRefactoring(fm_model).transform()

    uvl_level = FMLanguageLevel().execute(fm_model).get_result().major.name
    if uvl_level == 'BOOLEAN' and not any (attr.attribute_type.value in ['Integer', 'Real']  for attr in fm_model.get_attributes()):
        return  # Skip boolean-only models
    
    for operation in operations:
        result = execute_operation_on_model(model_name, fm_path, operation, n_runs)
        if result:
            write_results_incrementally(OUTPUT_CSV, CSV_HEADERS, [result])   


def execute_operation_on_model(model_name: str,
                               fm_path: str,
                               Operation: Callable,
                               n_runs: int = N_RUNS) -> Optional[dict[str, Any]]:
    times: list[float] = []
    result = None
    is_timeout = False
    for _ in range(n_runs):
        try:
            with multiprocessing.Manager() as manager:
                shared_data = manager.dict({
                    'status': 'RUNNING',
                    'partial_result': 0,
                    'final_result': None
                })
                process = multiprocessing.Process(target=worker_execute, args=(Operation, 
                                                                               fm_path, 
                                                                               shared_data))
                process.start()
                process.join(timeout=TIMEOUT)  # Wait for completion or timeout
                if process.is_alive():  # Timeout occurred
                    process.terminate()  # Stop the process (SIGTERM/SIGKILL)
                    process.join()  # Wait for termination (necessary to free resources)

                    # Report timeout status and partial result
                    result = shared_data.get('partial_result', None)
                    shared_data['status'] = 'TIMEOUT'
                    is_timeout = True
                    break  # No need to continue repetitions on timeout
                if shared_data['status'] == 'COMPLETED':
                    result = shared_data['final_result']
                    result = len(result) if isinstance(result, list) else result
                    times.append(shared_data['elapsed_time'])
                elif shared_data['status'].startswith('ERROR'):
                    result = shared_data['status']
                    print(f'❌ Worker Error executing {Operation.__name__} on model from {model_name}: {result}')
                    break  # Stop on error
        except Exception as e:
            print(f'❌ Error executing {Operation.__name__} on model from {model_name}: {e}')
            return
    if times:
        mean_time = round(statistics.mean(times), PRECISION)
        median_time = round(statistics.median(times), PRECISION)
        stddev_time = round(statistics.stdev(times), PRECISION) if len(times) > 1 else 0.0
    else:
        mean_time = median_time = stddev_time = 0.0
    row_data = {
            KEY_MODEL_NAME: model_name,
            KEY_OPERATION: Operation.__name__,
            KEY_RESULT: str(result),
            KEY_RUNS: len(times),
            KEY_TIME_MEAN: mean_time,
            KEY_TIME_MEDIAN: median_time,
            KEY_TIME_STDDEV: stddev_time,
            KEY_TIMEOUT: str(TIMEOUT) if is_timeout else str(None)
        }
    return row_data


def get_operations_to_run(operation_filter: str) -> list[Operation]:
    if operation_filter.lower() == 'all':
        return list(OPERATIONS.values())
    if operation_filter in OPERATIONS:
        return [OPERATIONS[operation_filter]]
    raise ValueError(f"🛑 Operation '{operation_filter}' not found in registry." \
                     f" Available operations: {list(OPERATIONS.keys())}")


def main():
    parser = argparse.ArgumentParser(description='AAFM Analysis', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('models_dir', type=str, help='Directory containing the feature model files (e.g., resources/models/uvl_models).')
    parser.add_argument('--operation', type=str, default='all', help=f'Specific operation to benchmark. Use "all" to run all registered operations. 'f'(See BenchmarkRunner.MASTER_OPERATION_REGISTRY for available names)')
    parser.add_argument('--output_file', type=str, default=OUTPUT_CSV, help='Name of the output CSV file.')
    
    args = parser.parse_args()
    models_dir = args.models_dir
    target_op_name = args.operation
    output_csv = args.output_file

    print(f"🚀 Starting Feature Model Benchmark")

    operations_to_run = get_operations_to_run(target_op_name)
    model_paths_to_run = get_models_to_run(models_dir, output_csv)
    num_to_run = len(model_paths_to_run)
    for i, model_path in enumerate(model_paths_to_run):
        print(f"[PROGRESS: {i+1}/{num_to_run}] Analyzing {Path(model_path).name}...")
        analyze_model(model_path, operations_to_run)
        
        
    print("✅ Full Benchmark Process Completed.")


if __name__ == "__main__":
    main()