from flamapy.core.discover import DiscoverMetamodels

from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3Configurations,
    Z3ConfigurationsNumber,
    Z3CoreFeatures,
    Z3DeadFeatures
)


MODEL = 'resources/models/uvl_models/Electricity.uvl'


def main():
    dm = DiscoverMetamodels()
    fm_model = dm.use_transformation_t2m(MODEL, 'fm')
    print(fm_model)
    z3_model = FmToZ3(fm_model).transform()
    print(z3_model)

    result = Z3Satisfiable().execute(z3_model).get_result()
    print(f'Satisfiable: {result}')

    core_features = Z3CoreFeatures().execute(z3_model).get_result()
    print(f'Core features: {core_features}')

    dead_features = Z3DeadFeatures().execute(z3_model).get_result()
    print(f'Dead features: {dead_features}')

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