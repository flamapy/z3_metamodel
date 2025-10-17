import logging
from flamapy.metamodels.fm_metamodel.transformations import UVLReader
from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3Configurations,
    Z3ConfigurationsNumber,
    Z3CoreFeatures,
    Z3DeadFeatures,
    Z3FalseOptionalFeatures,
    Z3AttributeOptimization,
    Z3SatisfiableConfiguration
)
from flamapy.metamodels.z3_metamodel.operations.interfaces import OptimizationGoal

from flamapy.metamodels.configuration_metamodel.transformations import ConfigurationJSONReader


logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


MODEL = 'resources/models/uvl_models/icecream_attributes.uvl'
#MODEL = 'resources/models/uvl_models/Pizza_z3.uvl'
CONFIG = 'resources/configs/icecream_attributes.json'


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
        config_str = ', '.join(f'{f}={v}' if not isinstance(v, bool) else f'{f}' for f,v in config.elements.items() if config.is_selected(f))
        print(f'Config. {i}: {config_str}')

    core_features = Z3CoreFeatures().execute(z3_model).get_result()
    print(f'Core features: {core_features}')

    dead_features = Z3DeadFeatures().execute(z3_model).get_result()
    print(f'Dead features: {dead_features}')

    false_optional_features = Z3FalseOptionalFeatures().execute(z3_model).get_result()
    print(f'False optional features: {false_optional_features}')

    attributes = fm_model.get_attributes()
    print('Attributes in the model')
    for attr in attributes:
        print(f' - {attr.name} ({attr.attribute_type})')
    
    attribute_optimization_op = Z3AttributeOptimization()
    attributes = {'Price': OptimizationGoal.MINIMIZE,
                  'Cost': OptimizationGoal.MAXIMIZE}
    attribute_optimization_op.set_attributes(attributes)
    configurations_with_values = attribute_optimization_op.execute(z3_model).get_result()
    print(f'Optimum configurations: {len(configurations_with_values)} configs.')
    # for i, config_value in enumerate(configurations_with_values, 1):
    #     config, values = config_value
    #     values_str = ', '.join(f'{k}={v}' for k,v in values.items())
    #     print(f'Config. {i}: {config.elements} | Values: {values_str}')
    for i, config_value in enumerate(configurations_with_values, 1):
        config, values = config_value
        config_str = ', '.join(f'{f}={v}' if not isinstance(v, bool) else f'{f}' for f,v in config.elements.items() if config.is_selected(f))
        values_str = ', '.join(f'{k}={v}' for k,v in values.items())
        print(f'Config. {i}: {config_str} | Values: {values_str}')

    n_configs = Z3ConfigurationsNumber().execute(z3_model).get_result()
    print(f'Configurations number: {n_configs}')

    configuration = ConfigurationJSONReader(CONFIG).transform()
    configuration.set_full(False)
    print(f'Configuration from {CONFIG}: {configuration.elements}')
    satisfiable_configuration_op = Z3SatisfiableConfiguration()
    satisfiable_configuration_op.set_configuration(configuration)
    is_satisfiable = satisfiable_configuration_op.execute(z3_model).get_result()
    print(f'Is the configuration satisfiable? {is_satisfiable}')

    configurations_op = Z3Configurations()
    configurations_op.set_partial_configuration(configuration)
    configurations = configurations_op.execute(z3_model).get_result()
    print(f'Configurations with partial configurations: {len(configurations)}')
    for i, config in enumerate(configurations, 1):
        config_str = ', '.join(f'{f}={v}' if not isinstance(v, bool) else f'{f}' for f,v in config.elements.items() if config.is_selected(f))
        print(f'Config. {i}: {config_str}')

    n_configs_op = Z3ConfigurationsNumber()
    n_configs_op.set_partial_configuration(configuration)
    n_configs = n_configs_op.execute(z3_model).get_result()
    print(f'Configurations number with partial configuration: {n_configs}')


if __name__ == "__main__":
    main()