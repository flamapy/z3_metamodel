from flamapy.core.discover import DiscoverMetamodels

from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.fm_metamodel.operations import FMEvaluateAttribute
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3Configurations,
    Z3ConfigurationsNumber,
    Z3CoreFeatures,
    Z3DeadFeatures,
    Z3FalseOptionalFeatures,
    Z3AttributeOptimization
)
from flamapy.metamodels.z3_metamodel.operations.interfaces import OptimizationGoal

MODEL = 'resources/models/uvl_models/fm02_z3.uvl'
#MODEL = 'resources/models/uvl_models/fm02_z3.uvl'
#MODEL = 'resources/models/uvl_models/tutorial_pizzas/Pizzas_01.uvl'

def main():
    fm_model = UVLReader(MODEL).transform()
    print(fm_model)
    z3_model = FmToZ3(fm_model).transform()
    print(z3_model)

    result = Z3Satisfiable().execute(z3_model).get_result()
    print(f'Satisfiable: {result}')

    configurations = Z3Configurations().execute(z3_model).get_result()
    print(f'Configurations: {len(configurations)}')
    for i, config in enumerate(configurations, 1):
        print(f'Config. {i}: {config.elements}')

    core_features = Z3CoreFeatures().execute(z3_model).get_result()
    print(f'Core features: {core_features}')

    dead_features = Z3DeadFeatures().execute(z3_model).get_result()
    print(f'Dead features: {dead_features}')

    false_optional_features = Z3FalseOptionalFeatures().execute(z3_model).get_result()
    print(f'False optional features: {false_optional_features}')

    attribute_optimization_op = Z3AttributeOptimization()
    attr_price = fm_model.get_attribute_by_name('Price')
    attr_cost = fm_model.get_attribute_by_name('Cost')
    attributes = {attr_price: OptimizationGoal.MAXIMIZE,
                  attr_cost: OptimizationGoal.MINIMIZE}
    attribute_optimization_op.set_attributes(attributes)
    configurations_with_values = attribute_optimization_op.execute(z3_model).get_result()
    print(f'Optimum configurations: {len(configurations_with_values)} configs.')
    for i, config_value in enumerate(configurations_with_values, 1):
        config, values = config_value
        values_str = ', '.join(f'{k}={v}' for k,v in values.items())
        print(f'Config. {i}: {config.elements} | Values: {values_str}')
    raise Exception

    configurations = Z3Configurations().execute(z3_model).get_result()
    print(f'Configurations: {len(configurations)}')
    for i, config in enumerate(configurations, 1):
        features_str = []
        for f,v in config.elements.items():
            if isinstance(v, bool) and v:
                features_str.append(str(f))
            elif v:
                features_str.append(f'{f}={v}')
        print(f'{i}: {", ".join(features_str)}')

    n_configs = Z3ConfigurationsNumber().execute(z3_model).get_result()
    print(f'Configurations number: {n_configs}')


if __name__ == "__main__":
    main()