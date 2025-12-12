import statistics
import argparse
import multiprocessing
from multiprocessing.managers import DictProxy
from pathlib import Path
from typing import Any, Optional, Callable

from flamapy.core.operations import Operation
from flamapy.metamodels.fm_metamodel.models import FeatureType
from flamapy.metamodels.fm_metamodel.transformations import UVLReader, FlatFM
from flamapy.metamodels.fm_metamodel.transformations.refactorings import FeatureCardinalityRefactoring
from flamapy.metamodels.fm_metamodel.operations import FMLanguageLevel
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3AllFeatureBounds
)
from custom_operations.z3_configurations_number import Z3ConfigurationsNumber

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
MODEL_NAME = 'Model_Name'
UVL_LEVEL = 'UVL_Level'
N_BOOLEAN_FEATURES = 'N_Boolean_Features'
N_INTEGER_FEATURES = 'N_Integer_Features'
N_REAL_FEATURES = 'N_Real_Features'
N_STRING_FEATURES = 'N_String_Features'
N_BOOLEAN_CONSTRAINTS = 'N_Boolean_Constraints'
N_ARITHMETIC_CONSTRAINTS = 'N_Arithmetic_Constraints'
N_AGGREGATE_CONSTRAINTS = 'N_Aggregate_Constraints'
N_BOOLEAN_VARIABLES = 'N_Boolean_Variables'
N_TYPED_VARIABLES = 'N_Typed_Variables'
N_ATTRIBUTE_VARIABLES = 'N_Attribute_Variables'
N_C_CROSS = 'N_C_Cross'
N_C_STRUCTURE = 'N_C_Structure'
N_C_LINK = 'N_C_Link'
N_C_ATTRIBUTE = 'N_C_Attribute'
TOTAL_CONSTRAINTS_SMT = 'Total_Constraints_SMT'
N_UNBOUNDED_VARIABLES = 'N_Unbounded_Variables'
SATISFIABLE = 'Satisfiable'
ERROR = 'Error'

CSV_HEADERS: list[str] = [
    MODEL_NAME,
    UVL_LEVEL,
    N_BOOLEAN_FEATURES,
    N_INTEGER_FEATURES,
    N_REAL_FEATURES,
    N_STRING_FEATURES,
    N_BOOLEAN_CONSTRAINTS,
    N_ARITHMETIC_CONSTRAINTS,
    N_AGGREGATE_CONSTRAINTS,
    N_BOOLEAN_VARIABLES,
    N_TYPED_VARIABLES,
    N_ATTRIBUTE_VARIABLES,
    N_C_STRUCTURE,
    N_C_CROSS,
    N_C_LINK,
    N_C_ATTRIBUTE,
    TOTAL_CONSTRAINTS_SMT,
    N_UNBOUNDED_VARIABLES,
    SATISFIABLE,
    ERROR
]


PRECISION = 4
OUTPUT_CSV = f'z3_benchmark_metrics_results.csv'


def analyze_model(fm_path: str) -> None:
    row_data = {}
    row_data[MODEL_NAME] = Path(fm_path).stem
    try:
        fm_model = UVLReader(fm_path).transform()
        # Flat the FM
        flat_op = FlatFM(fm_model)
        flat_op.set_maintain_namespaces(False)
        fm_model = flat_op.transform()

        # Refactor feature cardinalities
        #fm_model = FeatureCardinalityRefactoring(fm_model).transform()

        row_data[UVL_LEVEL] = FMLanguageLevel().execute(fm_model).get_result().major.name
        if row_data[UVL_LEVEL] == 'BOOLEAN' and not any (attr.attribute_type.value in ['Integer', 'Real']  for attr in fm_model.get_attributes()):
            return  # Skip boolean-only models
        row_data[N_BOOLEAN_FEATURES] = sum(f.feature_type == FeatureType.BOOLEAN for f in fm_model.get_features())
        row_data[N_INTEGER_FEATURES] = sum(f.feature_type == FeatureType.INTEGER for f in fm_model.get_features())
        row_data[N_REAL_FEATURES] = sum(f.feature_type == FeatureType.REAL for f in fm_model.get_features())
        row_data[N_STRING_FEATURES] = sum(f.feature_type == FeatureType.STRING for f in fm_model.get_features())
        row_data[N_BOOLEAN_CONSTRAINTS] = len(fm_model.get_logical_constraints())
        row_data[N_ARITHMETIC_CONSTRAINTS] = len(fm_model.get_arithmetic_constraints())
        row_data[N_AGGREGATE_CONSTRAINTS] = len(fm_model.get_aggregations_constraints())
        row_data[N_C_STRUCTURE] = sum(len(f.get_relations()) for f in fm_model.get_features())
        row_data[N_C_CROSS] = len(fm_model.get_constraints())

        z3_model = FmToZ3(fm_model).transform()
        row_data[N_BOOLEAN_VARIABLES] = sum(finfo.ftype == FeatureType.BOOLEAN for finfo in z3_model.features.values())
        row_data[N_TYPED_VARIABLES] = sum(finfo.ftype != FeatureType.BOOLEAN for finfo in z3_model.features.values())
        row_data[N_ATTRIBUTE_VARIABLES] = sum(len(attributes) for attributes in z3_model.attributes.values())
        row_data[N_C_LINK] = row_data[N_TYPED_VARIABLES]
        row_data[N_C_ATTRIBUTE] = row_data[N_ATTRIBUTE_VARIABLES] * 2
        row_data[TOTAL_CONSTRAINTS_SMT] = len(z3_model.constraints)

        variable_bounds = Z3AllFeatureBounds().execute(z3_model).get_result()
        row_data[N_UNBOUNDED_VARIABLES] = sum(not bounds['bounded'] for bounds in variable_bounds.values())
    
        satisfiable = Z3Satisfiable().execute(z3_model).get_result()
        row_data[SATISFIABLE] = satisfiable

        row_data[ERROR] = str(None)
    except Exception as e:
        row_data[ERROR] = f'ERROR: reading FM model from {fm_path}: {e}'
        

    if row_data:
        write_results_incrementally(OUTPUT_CSV, CSV_HEADERS, [row_data])   


def main():
    parser = argparse.ArgumentParser(description='AAFM Analysis', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('models_dir', type=str, help='Directory containing the feature model files (e.g., resources/models/uvl_models).')
    parser.add_argument('--output_file', type=str, default=OUTPUT_CSV, help='Name of the output CSV file.')
    
    args = parser.parse_args()
    models_dir = args.models_dir
    output_csv = args.output_file

    print(f"🚀 Starting Feature Model Benchmark")

    model_paths_to_run = get_models_to_run(models_dir, output_csv)
    num_to_run = len(model_paths_to_run)
    for i, model_path in enumerate(model_paths_to_run):
        print(f"[PROGRESS: {i+1}/{num_to_run}] Analyzing {Path(model_path).name}...")
        analyze_model(model_path)
        
        
    print("✅ Full Benchmark Process Completed.")


if __name__ == "__main__":
    main()