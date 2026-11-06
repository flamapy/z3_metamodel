from flamapy.core.manifest import OperationCapability, PluginManifest
from flamapy.core.models.language_level import LanguageLevel, MajorLevel, MinorLevel

# The SMT backend for typed/attributed feature models (TYPE major level). Costs are estimated
# milliseconds from the 2026-11-06 calibration (betty synthetic models at 1% and 30% constraint
# density, 20-10,000 features, plus JHipster and busybox; worst case, never decreasing): building
# the solver and the satisfiability/implication queries scale to 10,000 features, false-optional
# detection reaches 11 s there, and listing or counting configurations enumerates the models one
# by one (0.9 s already on the 20-feature calibration model).
_IMPLICATION_QUERIES = ((100, 1), (200, 3), (500, 9), (1000, 20), (5000, 41), (10000, 100))
_SAT_QUERY = ((200, 1), (500, 4), (1000, 6), (2000, 16), (10000, 40))

MANIFEST = PluginManifest(
    name='z3',
    extension='z3',
    supported_level=LanguageLevel(MajorLevel.TYPE, {
        MinorLevel.STRING_CONSTRAINTS, MinorLevel.AGGREGATE_FUNCTION,
        MinorLevel.GROUP_CARDINALITY}),
    transformation_cost_curve=((1000, 54), (2000, 88), (5000, 120), (10000, 250)),
    operations={
        'satisfiable': OperationCapability(cost_curve=_SAT_QUERY),
        'satisfiable_configuration': OperationCapability(cost_curve=_SAT_QUERY),
        'core_features': OperationCapability(cost_curve=_IMPLICATION_QUERIES),
        'dead_features': OperationCapability(cost_curve=_IMPLICATION_QUERIES),
        'false_optional_features': OperationCapability(
            cost_curve=((50, 2), (100, 3), (200, 8), (500, 29), (1000, 100), (2000, 420),
                        (5000, 2100), (10000, 11000))),
        'configurations_number': OperationCapability(max_features=30, cost=900),
        'configurations': OperationCapability(max_features=30, cost=900),
        'feature_bounds': OperationCapability(),
        'all_feature_bounds': OperationCapability(),
        # Single- and multi-objective (Pareto) optimization over typed attributes.
        'attribute_optimization': OperationCapability(),
    },
)
