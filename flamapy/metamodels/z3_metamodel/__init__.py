from flamapy.core.manifest import PluginManifest, OperationCapability
from flamapy.core.models.language_level import LanguageLevel, MajorLevel

# The SMT backend for typed/attributed feature models (TYPE major level).
MANIFEST = PluginManifest(
    name='z3',
    extension='z3',
    supported_level=LanguageLevel(MajorLevel.TYPE, set()),
    operations={
        'feature_bounds': OperationCapability(),
        'all_feature_bounds': OperationCapability(),
        'optimize_attributes': OperationCapability(),
    },
)
