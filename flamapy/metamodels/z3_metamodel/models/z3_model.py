import logging
from typing import Any, Optional
from dataclasses import dataclass

import z3

from flamapy.core.models import VariabilityModel

from flamapy.metamodels.fm_metamodel.models import FeatureType, AttributeType


LOGGER = logging.getLogger('Z3Model')


@dataclass
class FeatureInfo:
    name: str              # feature name
    sel: Any               # BoolRef
    val: Optional[Any]     # Int/Real/String Ref or None for pure boolean features
    ftype: FeatureType     # "bool", "int", "real", "string"
    attributes: dict[str, dict[str, Any]]  # attr_name -> {"var": z3var, "type": ...}


class Z3Model(VariabilityModel):
    
    DEFAULT_PRECISION = 4

    @staticmethod
    def get_extension() -> str:
        return "z3"

    def __init__(self) -> None:
        self.ctx = z3.Context()
        self.features: dict[str, FeatureInfo] = {}
        self.attributes: dict[str, list[Any]] = {}  # attr_name -> [z3var]
        self.attributes_types: dict[str, AttributeType] = {}  # attr_name -> AttributeType
        self.constraints: list[Any] = []  # list of z3 expressions
        self.original_model: Optional[VariabilityModel] = None

    def create_const(self, ftype: FeatureType | AttributeType, value: Any) -> Any:
        """Helper to create a Z3 constant of the given type with the given value."""
        if ftype in [FeatureType.INTEGER, AttributeType.INTEGER]:
            return z3.IntVal(int(value), ctx=self.ctx)
        if ftype in [FeatureType.REAL, AttributeType.REAL]:
            return z3.RealVal(float(value), ctx=self.ctx)
        if ftype in [FeatureType.STRING, AttributeType.STRING]:
            return z3.StringVal(str(value), ctx=self.ctx)
        if ftype in [FeatureType.BOOLEAN, AttributeType.BOOLEAN]:
            return z3.BoolVal(bool(value), ctx=self.ctx)
        raise ValueError("Unsupported type")

    def add_boolean_feature(self, name: str) -> Any:
        """Add a boolean feature with the given name."""
        sel = z3.Bool(name, ctx=self.ctx)
        self.features[name] = FeatureInfo(name=name, 
                                          sel=sel, 
                                          val=None, 
                                          ftype=FeatureType.BOOLEAN, 
                                          attributes={})
        return sel

    def add_typed_feature(self, 
                          name: str, 
                          ftype: FeatureType,
                          const_value: Optional[Any]=None,
                          neutral_when_unselected: Optional[Any]=None) -> tuple[Any, Any]:
        """Add a typed feature with the given name and type.

        It creates two variables: a boolean 'sel' indicating if the feature is selected,
        and a 'val' variable of the given type (Integer, Real, String).
        If const_value is given, it is imposed when the feature is selected.
        If neutral_when_unselected is given, the value is set to that when the feature is
        not selected (to avoid unwanted effects in optimization).
        """
        sel = z3.Bool(f"{name}_sel", ctx=self.ctx)
        if ftype == FeatureType.INTEGER:
            val = z3.Int(f"{name}_val", ctx=self.ctx)
            if neutral_when_unselected is not None:
                neutral = self.create_const(FeatureType.INTEGER, neutral_when_unselected)
            else:
                neutral = z3.IntVal(0, ctx=self.ctx)
        elif ftype == FeatureType.REAL:
            val = z3.Real(f"{name}_val", ctx=self.ctx)
            if neutral_when_unselected is not None:
                neutral = self.create_const(FeatureType.REAL, neutral_when_unselected)
            else:
                neutral = z3.RealVal(0.0, ctx=self.ctx)
        elif ftype == FeatureType.STRING:
            val = z3.String(f"{name}_val", ctx=self.ctx)
            if neutral_when_unselected is not None:
                neutral = self.create_const(FeatureType.STRING, neutral_when_unselected)
            else:
                neutral = z3.StringVal("", ctx=self.ctx)
        else:
            raise ValueError("Unsupported feature type")

        self.features[name] = FeatureInfo(name=name, sel=sel, val=val, ftype=ftype, attributes={})

        # If const_value is given, it is imposed when the feature is selected.
        if const_value is not None:  # Esto creo que se puede quitar
            const_expr = self.create_const(ftype, const_value)
            self.constraints.append(z3.Implies(sel, val == const_expr))

        # Neutralize the value when not selected to avoid unwanted effects in optimization
        # (this is optional depending on the semantics; useful if using Optimize without If(...))
        self.constraints.append(z3.Implies(z3.Not(sel), val == neutral))

        return sel, val

    def get_variable(self, name: str) -> Optional[FeatureInfo]:
        """Get the FeatureInfo of a feature by name."""
        return self.features.get(name, None)
    
    def add_attribute(self, 
                      feature_name: str, 
                      attr_name: str, 
                      attr_type: AttributeType, 
                      const_value: Optional[Any]=None) -> Optional[Any]:
        """Add an attribute to a feature (attributes are typed variables)."""
        if feature_name not in self.features:
            raise KeyError(feature_name)
        info = self.features[feature_name]
        var_name = f"{feature_name}.{attr_name}"
        if attr_type == AttributeType.INTEGER:
            var = z3.Int(var_name, ctx=self.ctx)
            default_value = self.create_const(AttributeType.INTEGER, 0)
        elif attr_type == AttributeType.REAL:
            var = z3.Real(var_name, ctx=self.ctx)
            default_value = self.create_const(AttributeType.REAL, 0.0)
        elif attr_type == AttributeType.STRING:
            var = z3.String(var_name, ctx=self.ctx)
            default_value = self.create_const(AttributeType.STRING, "")
        elif attr_type == AttributeType.BOOLEAN:
            var = z3.Bool(var_name, ctx=self.ctx)
            default_value = self.create_const(AttributeType.BOOLEAN, False)
        elif attr_type == AttributeType.NESTED:
            LOGGER.warning(f"Warning: Attribute {var_name} has NESTED type, " \
                           "which is not currently supported in Z3Model. Ignored.")
            var = None
        elif attr_type == AttributeType.VECTOR:
            LOGGER.warning(f"Warning: Attribute {var_name} has VECTOR type, " \
                           "which is not currently supported in Z3Model. Ignored.")
            var = None
        else:
            raise ValueError("Unsupported attribute type")

        if var is not None:
            info.attributes[attr_name] = {"var": var, "type": attr_type}

            # Create a global record of attributes as well to easy access attributes by name
            if attr_name not in self.attributes:
                self.attributes_types[attr_name] = attr_type
                self.attributes[attr_name] = []
            self.attributes[attr_name].append(var)

            # If a const_value is given, it is imposed when the feature is selected.
            if const_value is not None:
                const_expr = self.create_const(attr_type, const_value)
                self.constraints.append(z3.Implies(info.sel, var == const_expr))
            # Neutralize the attribute when the feature is not selected
            self.constraints.append(z3.Implies(z3.Not(info.sel), var == default_value))

        return var

    def add_constraint(self, constraint: z3.ExprRef) -> None:
        """Add an arbitrary Z3 constraint to the model."""
        self.constraints.append(constraint)

    def __str__(self) -> str:
        res = "Variables: Feature (Type), Bool var, Typed value):\r\n"
        for i, (feature_name, feature_info) in enumerate(self.features.items()):
            res += f"V{i}: {feature_name} ({feature_info.ftype.name}), " \
                   f"sel: {feature_info.sel}, val: {feature_info.val}\r\n"
        res += "Attributes:\r\n"
        for attr_name, attr_vars in self.attributes.items():
            res += f"  {attr_name}: {', '.join(str(v) for v in attr_vars)}\r\n"
        res += "Constraints:\r\n"
        for i, c in enumerate(self.constraints):
            res += f"C{i}: {c}\r\n"
        return res

    def __hash__(self) -> int:
        return hash(
            (
                self.features, self.attributes, tuple(sorted(self.constraints))
            )
        )

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Z3Model)
            and self.features == other.features
            and self.attributes == other.attributes
            and sorted(self.constraints) == sorted(other.constraints)
        )

    @staticmethod
    def create_feature_constraints(feature_value: Any,
                                   feature_info: FeatureInfo,
                                   context: z3.Context) -> list[z3.ExprRef]:
        """Create Z3 constraints for a single feature and its configured value."""
        constraints = []
        if feature_value is False:  # Case 1: Feature not selected (False)
            # Constraint: the selection variable (sel) must be False.
            constraints.append(feature_info.sel == z3.BoolVal(False, ctx=context))
        else:  # Case 2: Feature selected (True, Integer, Real, String)
            # Constraint A: the selection variable (sel) must be True.
            sel_var = feature_info.sel
            constraints.append(sel_var == z3.BoolVal(True, ctx=context))
            # Constraint B (Only for Features with value):
            if feature_info.ftype in [FeatureType.INTEGER, FeatureType.REAL, FeatureType.STRING]:
                # The value variable (val) must be equal to the configuration value.
                if feature_info.val is None:
                    raise ValueError(f'Feature {feature_info.name} has no value expression.')
                val_var = feature_info.val
                z3_value = Z3Model.get_z3_value(feature_value, feature_info.ftype, context)
                constraints.append(val_var == z3_value)    
        return constraints
    
    @staticmethod
    def get_z3_value(value: Any, ftype: FeatureType, context: z3.Context) -> z3.ExprRef:
        """Return a Z3 expression for a given Python configuration value."""
        z3_value = None
        if ftype == FeatureType.BOOLEAN:
            z3_value = z3.BoolVal(bool(value), ctx=context)
        elif ftype == FeatureType.INTEGER:
            z3_value = z3.IntVal(int(value), ctx=context)
        elif ftype == FeatureType.REAL:
            # Real values are mapped to RealVal. We use str() to preserve precision.
            z3_value = z3.RealVal(str(value), ctx=context)
        elif ftype == FeatureType.STRING:
            # Strings are mapped to Z3 String
            z3_value = z3.StringVal(str(value), ctx=context)
        else:
            raise ValueError(f"Feature type '{ftype}' not supported for Z3.")
        return z3_value

    @staticmethod
    def sum_attribute(model: 'Z3Model', attr_name: str) -> z3.ArithRef:
        """Return a Z3 expression representing the sum of the given attribute across 
        all features."""
        exprs = []
        for _, feature_info in model.features.items():
            attr = feature_info.attributes.get(attr_name)
            if attr is not None:
                if attr['type'] == AttributeType.INTEGER:
                    zero_val = z3.IntVal(0, ctx=model.ctx)
                else:  # REAL
                    zero_val = z3.RealVal(0.0, ctx=model.ctx)
                expr = z3.If(feature_info.sel, attr['var'], zero_val)
                exprs.append(expr)
        return z3.Sum(exprs) if exprs else z3.RealVal(0.0, ctx=model.ctx)