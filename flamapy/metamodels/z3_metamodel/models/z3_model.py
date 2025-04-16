from enum import Enum
from typing import Optional, Any, Union

import z3

from flamapy.core.models import VariabilityModel, ASTOperation

from flamapy.metamodels.fm_metamodel.models import FeatureType


def get_datatype(name: str, feature_type: FeatureType) -> Any:
    """Create a datatype for optional typed features."""
    data_type = None
    if feature_type == FeatureType.BOOLEAN:
        data_type = z3.BoolSort()
    elif feature_type == FeatureType.INTEGER:
        data_type = z3.IntSort()
    elif feature_type == FeatureType.REAL:
        data_type = z3.RealSort()
    elif feature_type == FeatureType.STRING:
        data_type = z3.StringSort()
    option_var = z3.Datatype(name)
    option_var.declare('None')
    option_var.declare('Some', ('val', data_type))
    return option_var.create()


class Z3Model(VariabilityModel):
    """A z3 representation of the feature model.

    It relies on the z3 library: https://github.com/z3prover
    """

    VARIABLE_TYPES: dict[FeatureType, callable] = {
        FeatureType.BOOLEAN: z3.Bool,
        FeatureType.INTEGER: z3.Int,
        FeatureType.REAL: z3.Real,
        FeatureType.STRING: z3.String
    }

    # Algebraic data types for optional typed features
    OPTION_INT = get_datatype('OptionInt', FeatureType.INTEGER)
    OPTION_REAL = get_datatype('OptionReal', FeatureType.REAL)
    OPTION_STRING = get_datatype('OptionString', FeatureType.STRING)
    OPTION_BOOLEAN = get_datatype('OptionBoolean', FeatureType.BOOLEAN)

    @staticmethod
    def get_extension() -> str:
        return 'z3'

    def __init__(self) -> None:
        self._boolean_features_variables: dict[str, z3.z3.ExprRef] = {}
        self._typed_features_variables: dict[str, z3.z3.DatatypeRef] = {}
        self._typed_features_types: dict[str, z3.z3.DatatypeRef] = {}
        self._formulas: list[z3.z3.ExprRef] = []

    def add_variable(self, feature: str, feature_type: FeatureType = FeatureType.BOOLEAN) -> None:
        """Add a feature to the model.

        It adds a variable to the z3 model considering that all features are booleans, but
        it also keeps track of the feature type for non-boolean features in the FM.
        """
        if feature_type == FeatureType.BOOLEAN:
            self._boolean_features_variables[feature] = z3.Bool(feature)
        else:
            #self._typed_features_variables[feature] = Z3Model.VARIABLE_TYPES[feature_type](feature)
            # Create a variable of the specified type
            typed_variable = None
            variable_type = None
            if feature_type == FeatureType.INTEGER:
                variable_type = Z3Model.OPTION_INT
            elif feature_type == FeatureType.REAL:
                variable_type = Z3Model.OPTION_REAL
            elif feature_type == FeatureType.STRING:
                variable_type = Z3Model.OPTION_STRING
            typed_variable = z3.Const(feature, Z3Model.OPTION_INT)
            self._typed_features_variables[feature] = typed_variable
            self._typed_features_types[feature] = variable_type
        
    def get_boolean_variable(self, feature: str) -> Optional[z3.z3.ExprRef]:
        """Get the boolean variable associated with the given feature."""
        if feature in self._boolean_features_variables:
            return self._boolean_features_variables[feature]
        elif feature in self._typed_features_variables:
            variable = self._typed_features_variables[feature]
            variable_type = self._typed_features_types[feature]
            return variable_type.is_Some(variable)
        return None
    
    def get_typed_variable(self, feature: str) -> Optional[z3.z3.ExprRef]:
        """Get the typed variable associated with the given features."""
        if feature in self._typed_features_variables:
            variable = self._typed_features_variables[feature]
            variable_type = self._typed_features_types[feature]
            return variable_type.val(variable)
        return None

    def get_variable_type(self, feature: str) -> Optional[z3.z3.DatatypeRef]:
        """Get the variable type associated with the given feature."""
        if feature in self._boolean_features_variables:
            return FeatureType.BOOLEAN
        else:
            return self._typed_features_types.get(feature, None)
    
    def has_variable(self, feature: str) -> bool:
        """Check if the variable associated with the given feature is present in the model."""
        return feature in self._boolean_features_variables or \
               feature in self._typed_features_variables
    
    def add_formula(self, *formula: tuple[z3.z3.ExprRef]) -> None:
        """Add a formula to the model."""
        self._formulas.extend(formula)

    @property
    def formulas(self):
        return self._formulas
    
    def __str__(self) -> str:
        """Return a string representation of the model."""
        features = self._boolean_features_variables.keys() | self._typed_features_variables.keys()
        res = f'Z3 MODEL: {len(features)} variables, {len(self._formulas)} formulas\n'
        res += 'VARIABLES:\n'
        
        for number, feature in enumerate(features, 1):
            res += f'{number}: {feature}'
            if feature in self._boolean_features_variables:
                res += f' (Boolean): {self._boolean_features_variables[feature]}\n'
            elif feature in self._typed_features_variables:
                feature_type = self.get_variable_type(feature)
                variable = self._typed_features_variables[feature]
                res += f' ({feature_type}): {variable}\n'
        res += 'FORMULAS:\n'
        for number, formula in enumerate(self._formulas, 1):
            res += f'{number}: {formula}\n'
        return res

