from flamapy.core.discover import DiscoverMetamodels

from flamapy.metamodels.fm_metamodel.transformations.refactorings import FeatureCardinalityRefactoring


MODEL = 'tests/models/fm09_clones.uvl'


def main():
    dm = DiscoverMetamodels()
    fm_model = dm.use_transformation_t2m(MODEL, 'fm')

    fc_ref = FeatureCardinalityRefactoring(fm_model)
    instances = fc_ref.get_instances()
    while instances:
        instance = instances.pop()
        print(f'Instance: {instance}')
        fm_model = fc_ref.apply(instance)
        fc_ref = FeatureCardinalityRefactoring(fm_model)
        instances = fc_ref.get_instances()
    dm.use_transformation_m2t(fm_model, 'tests/models/fm09_clones_3.uvl')


if __name__ == "__main__":
    main()