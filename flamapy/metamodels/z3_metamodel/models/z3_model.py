from typing import Any, Optional
from dataclasses import dataclass

import z3

from flamapy.core.exceptions import FlamaException
from flamapy.core.models import VariabilityModel, ASTOperation

from flamapy.metamodels.fm_metamodel.models import FeatureType


@dataclass
class FeatureInfo:
    name: str              # feature name
    sel: Any               # BoolRef
    val: Optional[Any]     # Int/Real/String Ref or None for pure boolean features
    ftype: FeatureType     # "bool", "int", "real", "string"
    attributes: dict[str, dict[str, Any]]  # attr_name -> {"var": z3var, "type": ...}


class Z3Model:
    def __init__(self):
        self.features: dict[str, FeatureInfo] = {}
        self.attributes: dict[str, list[Any]] = {}  # attr_name -> [z3var]
        self.constraints = []  # list of z3 expressions
        self.original_model: Optional[VariabilityModel] = None

    def _const(self, ftype: FeatureType, value: Any) -> Any:
        """Helper to create a Z3 constant of the given type with the given value."""
        if ftype == FeatureType.INTEGER:
            return z3.IntVal(int(value))
        if ftype == FeatureType.REAL:
            return z3.RealVal(float(value))
        if ftype == FeatureType.STRING:
            return z3.StringVal(str(value))
        if ftype == FeatureType.BOOLEAN:
            return z3.BoolVal(bool(value))
        raise ValueError("Unsupported type")

    def add_boolean_feature(self, name: str):
        """Add a boolean feature with the given name."""
        sel = z3.Bool(name)
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
                          neutral_when_unselected: Optional[Any]=None):
        """Add a typed feature with the given name and type.

        It creates two variables: a boolean 'sel' indicating if the feature is selected,
        and a 'val' variable of the given type (Integer, Real, String).
        If const_value is given, it is imposed when the feature is selected.
        If neutral_when_unselected is given, the value is set to that when the feature is
        not selected (to avoid unwanted effects in optimization).
        """
        sel = z3.Bool(f"{name}_sel")
        if ftype == FeatureType.INTEGER:
            val = z3.Int(f"{name}_val")
            neutral = z3.IntVal(0) if neutral_when_unselected is None else self._const(FeatureType.INTEGER, neutral_when_unselected)
        elif ftype == FeatureType.REAL:
            val = z3.Real(f"{name}_val")
            neutral = z3.RealVal(0.0) if neutral_when_unselected is None else self._const(FeatureType.REAL, neutral_when_unselected)
        elif ftype == FeatureType.STRING:
            val = z3.String(f"{name}_val")
            neutral = z3.StringVal("") if neutral_when_unselected is None else self._const(FeatureType.STRING, neutral_when_unselected)
        else:
            raise ValueError("Unsupported feature type")

        self.features[name] = FeatureInfo(name=name, sel=sel, val=val, ftype=ftype, attributes={})

        # If const_value is given, it is imposed when the feature is selected.
        if const_value is not None:  # Esto creo que se puede quitar
            const_expr = self._const(ftype, const_value)
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
                      attr_type: FeatureType, 
                      const_value: Optional[Any]=None):
        """Add an attribute to a feature (attributes are typed variables)."""
        if feature_name not in self.features:
            raise KeyError(feature_name)
        info = self.features[feature_name]
        var_name = f"{feature_name}.{attr_name}"
        if attr_type == FeatureType.INTEGER:
            var = z3.Int(var_name)
        elif attr_type == FeatureType.REAL:
            var = z3.Real(var_name)
        elif attr_type == FeatureType.STRING:
            var = z3.String(var_name)
        elif attr_type == FeatureType.BOOLEAN:
            var = z3.Bool(var_name)
        else:
            raise ValueError("Unsupported attribute type")

        info.attributes[attr_name] = {"var": var, "type": attr_type}

        # Create a global record of attributes as well to easy access attributes by name
        if attr_name not in self.attributes:
            self.attributes[attr_name] = []
        self.attributes[attr_name].append(var)

        # If a const_value is given, it is imposed when the feature is selected.
        if const_value is not None:
            const_expr = self._const(attr_type, const_value)
            self.constraints.append(z3.Implies(info.sel, var == const_expr))

        return var

    def add_constraint(self, constraint: z3.ExprRef):
        """Add an arbitrary Z3 constraint to the model."""
        self.constraints.append(constraint)

    def __str__(self) -> str:
        res = "Variables: Feature (Type), Bool var, Typed value):\r\n"
        for i, (feature_name, feature_info) in enumerate(self.features.items()):
            res += f"V{i}: {feature_name} ({feature_info.ftype.name}), sel: {feature_info.sel}, val: {feature_info.val}\r\n"
        res += "Constraints:\r\n"
        for i, c in enumerate(self.constraints):
            res += f"C{i}: {c}\r\n"
        return res

    def __hash__(self) -> int:
        return hash(
            (
                self.features
            )
        )

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Z3Model)
            and self.features == other.features
            and sorted(self.constraints) == sorted(other.constraints)
        )

    # Construir la suma total de un atributo numérico (solo considera features con dicho atributo)
    # def sum_attribute(self, attr_name: str):
    #     exprs = []
    #     numeric_kind = None
    #     for fname, info in self.features.items():
    #         attr = info.attributes.get(attr_name)
    #         if not attr:
    #             continue
    #         sel = info.sel
    #         var = attr["var"]
    #         t = attr["type"]
    #         # Si mezcla int/real, hay que acordarlo a un único tipo (prefiere real)
    #         if t == "int":
    #             zero = IntVal(0)
    #         elif t == "real":
    #             zero = RealVal(0.0)
    #         else:
    #             raise ValueError("sum_attribute only supports numeric types (int/real)")
    #         exprs.append(If(sel, var, zero))
    #         if numeric_kind is None:
    #             numeric_kind = t
    #         elif numeric_kind != t:
    #             # mezcla int/real detectada -> recomendable convertir Int->Real con ToReal si lo deseas
    #             pass
    #     if not exprs:
    #         return IntVal(0)  # ó RealVal(0.0) según contexto
    #     return Sum(exprs)

    # # Optimización minimizando un atributo (ejemplo)
    # def minimize_attribute(self, attr_name: str):
    #     opt = Optimize()
    #     for c in self.constraints:
    #         opt.add(c)
    #     total = self.sum_attribute(attr_name)
    #     opt.minimize(total)
    #     if opt.check() ==  sat:
    #         m = opt.model()
    #         return m, total
    #     return None, None
    