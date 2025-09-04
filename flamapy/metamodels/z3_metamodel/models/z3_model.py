from typing import Any, Optional

import z3

from flamapy.core.exceptions import FlamaException
from flamapy.core.models import VariabilityModel, ASTOperation

from flamapy.metamodels.fm_metamodel.models import FeatureType


def get_datatype(name: str, variable_type: FeatureType) -> Any:
    """Create a datatype for optional typed variables.
    
    It uses algebraic data types (ADTs) to define variables that may or may not have a value.
    The ADT has two constructors:
        1. None: represents the absence of a value.
        2. Some: wraps a value of the specified type.
    """
    data_type = None
    if variable_type == FeatureType.BOOLEAN:
        data_type = z3.BoolSort()
    elif variable_type == FeatureType.INTEGER:
        data_type = z3.IntSort()
    elif variable_type == FeatureType.REAL:
        data_type = z3.RealSort()
    elif variable_type == FeatureType.STRING:
        data_type = z3.StringSort()
    else:
        raise FlamaException(f'Unsupported variable type: {variable_type}')
    option_var = z3.Datatype(name)
    option_var.declare('None')
    option_var.declare('Some', ('val', data_type))
    return option_var.create()


class Z3Model(VariabilityModel):
    """A z3 representation of the feature model.

    It relies on the z3 library: https://github.com/z3prover
    """

    # Algebraic data types for optional typed features
    OPTION_INT = get_datatype('OptionInt', FeatureType.INTEGER)
    OPTION_REAL = get_datatype('OptionReal', FeatureType.REAL)
    OPTION_STRING = get_datatype('OptionString', FeatureType.STRING)
    # The Option Boolean is not used, but defined for completeness
    OPTION_BOOLEAN = get_datatype('OptionBoolean', FeatureType.BOOLEAN)  

    DEFAULT_PRECISION = 2

    @staticmethod
    def get_extension() -> str:
        return 'z3'

    def __init__(self) -> None:
        self._boolean_features_variables: dict[str, z3.z3.ExprRef] = {}
        self._typed_features_variables: dict[str, z3.z3.DatatypeRef] = {}
        self._typed_variable_types: dict[str, z3.z3.DatatypeRef] = {}
        self._formulas: list[z3.z3.ExprRef] = []
        self.original_model: VariabilityModel

    def add_variable(self, name: str, variable_type: FeatureType = FeatureType.BOOLEAN) -> None:
        """Add a variable to the model.

        It adds a variable to the z3 model considering that all variables are booleans, but
        it also keeps track of the variable type for non-boolean variables.
        """
        if variable_type == FeatureType.BOOLEAN:
            self._boolean_features_variables[name] = z3.Bool(name)
        else:
            # Create a variable of the specified type
            if variable_type == FeatureType.INTEGER:
                adt_type = Z3Model.OPTION_INT
            elif variable_type == FeatureType.REAL:
                adt_type = Z3Model.OPTION_REAL
            elif variable_type == FeatureType.STRING:
                adt_type = Z3Model.OPTION_STRING
            else:
                raise FlamaException(f'Unsupported variable type: {variable_type}')
            typed_variable = z3.Const(name, adt_type)
            self._typed_features_variables[name] = typed_variable
            self._typed_variable_types[name] = adt_type
        
    def get_boolean_variable(self, name: str) -> Optional[z3.z3.ExprRef]:
        """Get the boolean variable associated with the given name."""
        variable = None
        if name in self._boolean_features_variables:
            variable = self._boolean_features_variables[name]
        elif name in self._typed_features_variables:
            var = self._typed_features_variables[name]
            variable_type = self._typed_variable_types[name]
            variable = variable_type.is_Some(var)
        return variable
    
    def get_typed_variable(self, name: str) -> Optional[z3.z3.ExprRef]:
        """Get the typed variable associated with the given name."""
        variable = None
        if name in self._typed_features_variables:
            var = self._typed_features_variables[name]
            variable_type = self._typed_variable_types[name]
            variable = variable_type.val(var)
        return variable

    def get_variable_type(self, name: str) -> Optional[z3.z3.DatatypeRef]:
        """Get the type of the variable associated with the given name."""
        if name in self._boolean_features_variables:
            return FeatureType.BOOLEAN  # TODO: change return type
        else:
            return self._typed_variable_types.get(name, None)
    
    def get_variables(self) -> set[z3.z3.ExprRef | z3.z3.DatatypeRef]:
        """Return all variables of the z3 model."""
        return set(self._boolean_features_variables.values()) | set(self._typed_features_variables.values())
    
    def get_variables_names(self) -> set[str]:
        """Return all variables names of the z3 model."""
        return self._boolean_features_variables.keys() | self._typed_features_variables.keys()
    
    def has_variable(self, name: str) -> bool:
        """Check if the variable associated with the given name is present in the model."""
        return name in self._boolean_features_variables or \
               name in self._typed_features_variables
    
    def add_formula(self, *formula: tuple[z3.z3.ExprRef]) -> None:
        """Add a formula to the model."""
        self._formulas.extend(formula)

    @property
    def formulas(self):
        return self._formulas
    
    def __str__(self) -> str:
        """Return a string representation of the z3 model."""
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

