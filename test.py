from flamapy.core.discover import DiscoverMetamodels

from flamapy.metamodels.z3_metamodel.transformations import FmToZ3
from flamapy.metamodels.z3_metamodel.operations import Z3Satisfiable


MODEL = 'tests/models/fm01.uvl'


def main():
    dm = DiscoverMetamodels()
    fm_model = dm.use_transformation_t2m(MODEL, 'fm')
    z3_model = FmToZ3(fm_model).transform()
    print(z3_model)

    result = Z3Satisfiable().execute(z3_model).get_result()
    print(f'Satisfiable: {result}')


if __name__ == "__main__":
    main()