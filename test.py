from flamapy.core.discover import DiscoverMetamodels

from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import (
    Z3Satisfiable,
    Z3Configurations
)


MODEL = 'tests/models/fm02.uvl'


def main():
    dm = DiscoverMetamodels()
    fm_model = dm.use_transformation_t2m(MODEL, 'fm')
    z3_model = FmToZ3(fm_model).transform()
    print(z3_model)

    #raise Exception
    result = Z3Satisfiable().execute(z3_model).get_result()
    print(f'Satisfiable: {result}')

    #raise Exception
    configurations = Z3Configurations().execute(z3_model).get_configurations()
    print(f'Configurations: {len(configurations)}')
    for i, config in enumerate(configurations, 1):
        features_str = []
        for f,v in config.elements.items():
            if isinstance(v, bool) and v:
                features_str.append(str(f))
            elif v:
                features_str.append(f'{f}={v}')
        print(f'{i}: {", ".join(features_str)}')


if __name__ == "__main__":
    main()