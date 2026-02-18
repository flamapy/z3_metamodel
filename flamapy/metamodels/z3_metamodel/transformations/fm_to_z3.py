import itertools
import logging
from typing import Any, Optional

import z3

from flamapy.core.models.ast import (
    ASTOperation,
    Node,
    LOGICAL_OPERATORS,
    ARITHMETIC_OPERATORS,
    AGGREGATION_OPERATORS
)

from flamapy.core.exceptions import FlamaException
from flamapy.core.transformations import ModelToModel
from flamapy.metamodels.fm_metamodel.models import (
    FeatureModel,
    Feature,
    Relation,
    Constraint,
    FeatureType,
    AttributeType
)

from flamapy.metamodels.z3_metamodel.models import Z3Model, FeatureInfo


LOGGER = logging.getLogger('FmToZ3')


# Map each binary AST operation to the corresponding Z3 expression builder.
_BINARY_OPS: dict[ASTOperation, Any] = {
    ASTOperation.AND: z3.And,
    ASTOperation.OR: z3.Or,
    ASTOperation.IMPLIES: z3.Implies,
    ASTOperation.REQUIRES: z3.Implies,
    ASTOperation.EXCLUDES: lambda lhs, rhs: z3.Implies(lhs, z3.Not(rhs)),
    ASTOperation.XOR: z3.Xor,
    ASTOperation.EQUIVALENCE: lambda lhs, rhs: (lhs == rhs),
    ASTOperation.ADD: lambda lhs, rhs: (lhs + rhs),
    ASTOperation.SUB: lambda lhs, rhs: (lhs - rhs),
    ASTOperation.MUL: lambda lhs, rhs: (lhs * rhs),
    ASTOperation.DIV: lambda lhs, rhs: (lhs / rhs),
    ASTOperation.EQUALS: lambda lhs, rhs: (lhs == rhs),
    ASTOperation.LOWER: lambda lhs, rhs: (lhs < rhs),
    ASTOperation.GREATER: lambda lhs, rhs: (lhs > rhs),
    ASTOperation.LOWER_EQUALS: lambda lhs, rhs: (lhs <= rhs),
    ASTOperation.GREATER_EQUALS: lambda lhs, rhs: (lhs >= rhs),
    ASTOperation.NOT_EQUALS: lambda lhs, rhs: (lhs != rhs),
}


class FmToZ3(ModelToModel):

    @staticmethod
    def get_source_extension() -> str:
        return "fm"

    @staticmethod
    def get_destination_extension() -> str:
        return "z3"

    def __init__(self, source_model: FeatureModel) -> None:
        self.source_model = source_model
        self.destination_model: Z3Model = Z3Model()
        self._counter: int = 0

    def transform(self) -> Z3Model:
        self.destination_model = Z3Model()
        self.destination_model.original_model = self.source_model
        self._declare_features()
        self._traverse_feature_tree()
        self._traverse_constraints()
        return self.destination_model

    def _declare_features(self) -> None:
        for feature in self.source_model.get_features():
            if feature.feature_type == FeatureType.BOOLEAN:
                self.destination_model.add_boolean_feature(feature.name)
            else:
                self.destination_model.add_typed_feature(feature.name, feature.feature_type)
            self._declare_attributes(feature)
            self._counter += 1

    def _declare_attributes(self, feature: Feature) -> None:
        for attribute in feature.get_attributes():
            if attribute.attribute_type is not None:
                self.destination_model.add_attribute(feature.name,
                                                     attribute.name,
                                                     attribute.attribute_type,
                                                     attribute.default_value)

    def _traverse_feature_tree(self) -> None:
        """Traverse the feature tree from the root,
        adding variables and constraints to the Z3 model."""
        if self.source_model is None or self.source_model.root is None:
            return None
        # The root is always present
        root_feature = self.source_model.root
        variable = self.destination_model.get_variable(root_feature.name)
        if variable is None:
            raise FlamaException(f'Unsupported root feature: {root_feature.name}')
        formula = variable.sel
        self.destination_model.add_constraint(formula)
        features = [root_feature]
        while features:
            feature = features.pop()
            for relation in feature.get_relations():
                self._add_relation_formula(relation)
                features.extend(relation.children)

    def _traverse_constraints(self) -> None:
        # We first process non-aggregation constraints
        # That is because aggregation constraints may depend on other constraints
        # where other constraints may define variables used in the aggregation
        aggregation_constraints = []
        for constraint in self.source_model.get_constraints():
            if constraint.is_aggregation_constraint():
                aggregation_constraints.append(constraint)
            else:
                self._add_constraint_formula(constraint)
        for agg_ctc in aggregation_constraints:
            self._add_constraint_formula(agg_ctc)

    def _add_relation_formula(self, relation: Relation) -> None:
        if relation.is_mandatory():
            self._add_mandatory_formula(relation)
        elif relation.is_optional():
            self._add_optional_formula(relation)
        elif relation.is_or():
            self._add_or_formula(relation)
        elif relation.is_alternative():
            self._add_alternative_formula(relation)
        elif relation.is_mutex():
            self._add_mutex_formula(relation)
        elif relation.is_cardinal():
            self._add_cardinality_formula(relation)

    def _add_mandatory_formula(self, relation: Relation) -> None:
        parent_variable = self.destination_model.get_variable(relation.parent.name)
        if parent_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_variable.sel
        child_variable = self.destination_model.get_variable(relation.children[0].name)
        if child_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.children[0].name}')
        child = child_variable.sel
        formula = (parent == child)
        self.destination_model.add_constraint(formula)

    def _add_optional_formula(self, relation: Relation) -> None:
        parent_variable = self.destination_model.get_variable(relation.parent.name)
        if parent_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_variable.sel
        child_variable = self.destination_model.get_variable(relation.children[0].name)
        if child_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.children[0].name}')
        child = child_variable.sel
        formula = z3.Implies(child, parent)
        self.destination_model.add_constraint(formula)

    def _add_or_formula(self, relation: Relation) -> None:
        parent_variable = self.destination_model.get_variable(relation.parent.name)
        if parent_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_variable.sel
        children = []
        for child in relation.children:
            child_variable = self.destination_model.get_variable(child.name)
            if child_variable is None:
                raise FlamaException(f'Unsupported feature: {child.name}')
            children.append(child_variable.sel)
        formula = (parent == z3.Or(*children))
        self.destination_model.add_constraint(formula)

    def _add_alternative_formula(self, relation: Relation) -> None:
        formulas = []
        parent_variable = self.destination_model.get_variable(relation.parent.name)
        if parent_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_variable.sel
        children = []
        for child in relation.children:
            child_variable = self.destination_model.get_variable(child.name)
            if child_variable is None:
                raise FlamaException(f'Unsupported feature: {child.name}')
            children.append(child_variable.sel)
        for child in children:
            children_negatives = set(children) - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        self.destination_model.add_constraint(formula)

    def _add_mutex_formula(self, relation: Relation) -> None:
        formulas = []
        parent_variable = self.destination_model.get_variable(relation.parent.name)
        if parent_variable is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_variable.sel
        children = set()
        for child in relation.children:
            child_variable = self.destination_model.get_variable(child.name)
            if child_variable is None:
                raise FlamaException(f'Unsupported feature: {child.name}')
            children.add(child_variable.sel)
        for child in children:
            children_negatives = children - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        formula = z3.Or(parent == z3.Not(z3.Or(*children)), formula)
        self.destination_model.add_constraint(formula)

    def _build_literals(self, children: list[Any], combination: tuple[Any, ...]) -> list[Any]:
        """Build a list of Z3 literals for a cardinality combination."""
        return [ch if ch in combination else z3.Not(ch) for ch in children]

    def _add_active_parent_constraints(self,
                                       parent: Any,
                                       children: list[Any],
                                       card_min: int,
                                       card_max: int) -> None:
        """Add constraints enforced when the parent feature is active."""
        for val in range(len(children) + 1):
            if val < card_min or val > card_max:
                for combination in itertools.combinations(children, val):
                    literals = self._build_literals(children, combination)
                    self.destination_model.add_constraint(
                        z3.Implies(parent, z3.Not(z3.And(*literals)))
                    )

    def _add_inactive_parent_constraints(self, parent: Any, children: list[Any]) -> None:
        """Add constraints enforced when the parent feature is inactive."""
        for val in range(1, len(children) + 1):
            for combination in itertools.combinations(children, val):
                literals = self._build_literals(children, combination)
                self.destination_model.add_constraint(
                    z3.Implies(z3.Not(parent), z3.Not(z3.And(*literals)))
                )

    def _add_cardinality_formula(self, relation: Relation) -> None:
        parent_var = self.destination_model.get_variable(relation.parent.name)
        if parent_var is None:
            raise FlamaException(f'Unsupported feature: {relation.parent.name}')
        parent = parent_var.sel
        children = []
        for child in relation.children:
            child_var = self.destination_model.get_variable(child.name)
            if child_var is None:
                raise FlamaException(f'Unsupported feature: {child.name}')
            children.append(child_var.sel)
        card_min = relation.card_min
        card_max = relation.card_max if relation.card_max != -1 else len(children)
        self._add_active_parent_constraints(parent, children, card_min, card_max)
        self._add_inactive_parent_constraints(parent, children)

    def _add_constraint_formula(self, ctc: Constraint) -> None:
        expr = self._get_expression(ctc.ast.root, None)
        self.destination_model.add_constraint(expr)

    def _get_expression(self, node: Node, parent: Optional[Node]) -> z3.ExprRef:
        if node.is_term():
            return self._get_term_expression(node, parent)
        if node.is_binary_op():
            return self._get_binary_op_expression(node)
        if node.is_unary_op():
            left_expr = self._get_expression(node.left, node)
            if node.data == ASTOperation.NOT:
                return z3.Not(left_expr)
            raise FlamaException(f'Unsupported unary operator: {node.data}')
        if node.is_aggregate_op():
            return self._get_aggregate_op_expression(node)
        raise FlamaException(f'Unsupported node type: {node}')

    def _get_term_expression(self, node: Node, parent: Optional[Node]) -> z3.ExprRef:
        """Handle terminal node expressions."""
        if parent is None:
            return self._get_root_term_expression(node)
        if isinstance(node.data, str):
            return self._get_str_term_expression(node, parent)
        if isinstance(node.data, bool):
            return z3.BoolVal(node.data, ctx=self.destination_model.ctx)
        if isinstance(node.data, int):
            return z3.IntVal(node.data, ctx=self.destination_model.ctx)
        if isinstance(node.data, float):
            return z3.RealVal(node.data, ctx=self.destination_model.ctx)
        raise FlamaException(f'Unsupported constant type: {type(node.data)}')

    def _get_root_term_expression(self, node: Node) -> z3.ExprRef:
        """Handle a terminal node that is the root of a constraint (no parent)."""
        if not isinstance(node.data, str):
            raise FlamaException(f'Unsupported terminal feature: {type(node.data)}')
        expr = self.destination_model.get_variable(node.data)
        if expr is None:
            raise FlamaException(f'Unsupported feature: {node.data}')
        return expr.sel

    def _get_str_term_expression(self, node: Node, parent: Node) -> z3.ExprRef:
        """Handle a terminal string node that has a parent operator."""
        variable = self.destination_model.get_variable(node.data)
        if variable is not None:
            return self._get_feature_term_expression(variable, parent)
        if '.' in node.data:
            return self._get_attribute_term_expression(node.data)
        return z3.StringVal(node.data.strip("'\""), ctx=self.destination_model.ctx)

    def _get_feature_term_expression(self,
                                     variable: FeatureInfo,
                                     parent: Node) -> z3.ExprRef:
        """Return the Z3 sub-expression for a feature reference given its parent operator."""
        if parent.data in LOGICAL_OPERATORS:
            return variable.sel
        if parent.data in ARITHMETIC_OPERATORS:
            return variable.val
        if parent.data in AGGREGATION_OPERATORS:
            return variable
        raise FlamaException(f'Unsupported operator: {parent.data}')

    def _get_attribute_term_expression(self, identifier: str) -> z3.ExprRef:
        """Return the Z3 expression for an attribute reference (e.g. 'Feature.attr')."""
        feature_attribute = find_feature_and_attribute(self.destination_model, identifier)
        if feature_attribute is None:
            raise FlamaException(f'Unsupported feature or attribute: {identifier}')
        feature_name, attr_name = feature_attribute
        feature_info = self.destination_model.get_variable(feature_name)
        if feature_info is None:
            raise FlamaException(f'Unsupported feature in attribute: {feature_name}')
        attribute_info = feature_info.attributes.get(attr_name, None)
        if attribute_info is not None:
            return attribute_info['var']
        attribute = self.source_model.get_attribute_by_name(attr_name)
        if attribute is not None:
            return self.destination_model.add_attribute(
                feature_name, attr_name, attribute.attribute_type, None
            )
        raise FlamaException(f'Unsupported attribute: {attr_name} in feature {feature_name}')

    def _get_binary_op_expression(self, node: Node) -> z3.ExprRef:
        """Build a Z3 expression for a binary operator node."""
        left_expr = self._get_expression(node.left, node)
        right_expr = self._get_expression(node.right, node)
        op_fn = _BINARY_OPS.get(node.data)
        if op_fn is None:
            raise FlamaException(f'Unsupported binary operator: {node.data}')
        return op_fn(left_expr, right_expr)

    def _get_aggregate_op_expression(self, node: Node) -> z3.ExprRef:
        """Build a Z3 expression for an aggregation operator node."""
        left_expr = self._get_expression(node.left, node)
        right_expr = None
        if node.right is not None:
            right_expr = self._get_expression(node.right, node)
        if node.data in (ASTOperation.SUM, ASTOperation.AVG):
            return self._get_sum_avg_expression(node, left_expr, right_expr)
        if node.data == ASTOperation.LEN:
            return self._get_len_expression(left_expr)
        raise FlamaException(f'Unsupported aggregation operator: {node.data}')

    def _get_sum_avg_expression(self,
                                node: Node,
                                left_expr: Any,
                                right_expr: Optional[Any]) -> z3.ExprRef:
        """Build a Z3 expression for SUM or AVG aggregation."""
        attr_name = str(left_expr).strip("'\"")
        if right_expr is not None:
            feature = self.source_model.get_feature_by_name(right_expr.name)
            if feature is None:
                raise FlamaException(f'Unsupported feature: {right_expr.name}')
            attributes_vars = self._collect_attribute_vars(attr_name, feature)
        else:
            attributes_vars = self._collect_attribute_vars(attr_name, self.source_model.root)
        if node.data == ASTOperation.SUM:
            return z3.Sum(attributes_vars)
        if not attributes_vars:
            raise FlamaException('Cannot compute average over empty set')
        return z3.Sum(attributes_vars) / len(attributes_vars)

    def _collect_attribute_vars(self, attr_name: str, root_feature: Feature) -> list[Any]:
        """Collect Z3 attribute variables from the subtree rooted at root_feature."""
        attributes_vars = []
        for feat in get_subtree(root_feature):
            variable = self.destination_model.get_variable(feat.name)
            if variable is None:
                raise FlamaException(f'Unsupported feature: {feat.name}')
            feature_attributes = variable.attributes
            if attr_name in feature_attributes:
                attr_info = feature_attributes[attr_name]
                if attr_info['type'] == AttributeType.INTEGER:
                    zero_val = z3.IntVal(0, ctx=self.destination_model.ctx)
                else:
                    zero_val = z3.RealVal(0.0, ctx=self.destination_model.ctx)
                attributes_vars.append(z3.If(variable.sel, attr_info['var'], zero_val))
        return attributes_vars

    def _get_len_expression(self, left_expr: Any) -> z3.ExprRef:
        """Build a Z3 expression for the LEN aggregation operator."""
        if isinstance(left_expr, FeatureInfo):
            variable = self.destination_model.get_variable(left_expr.name)
            if variable is None:
                raise FlamaException(f'Unsupported feature: {left_expr.name}')
            return z3.Length(variable.val)
        if '.' in str(left_expr):
            return self._get_len_attribute_expression(str(left_expr))
        raise FlamaException(f'Unsupported LEN operand: {left_expr}')

    def _get_len_attribute_expression(self, identifier: str) -> z3.ExprRef:
        """Build a Z3 Length expression for an attribute reference."""
        feature_attribute = find_feature_and_attribute(self.destination_model, identifier)
        if feature_attribute is None:
            raise FlamaException(f'Unsupported feature or attribute: {identifier}')
        feature_name, attr_name = feature_attribute
        feature_info = self.destination_model.get_variable(feature_name)
        if feature_info is None:
            raise FlamaException(f'Unsupported feature in attribute: {feature_name}')
        attribute_info = feature_info.attributes.get(attr_name, None)
        if attribute_info is None:
            raise FlamaException(
                f'Unsupported attribute: {attr_name} in feature {feature_name}'
            )
        return z3.Length(attribute_info['var'])


def is_valid_feature(model: Z3Model, name: str) -> bool:
    return name in model.features


def is_valid_attribute(model: Z3Model, name: str) -> bool:
    return name in model.attributes


def find_feature_and_attribute(model: Z3Model, identifier: str) -> Optional[tuple[str, str]]:
    parts = identifier.split('.')
    n = len(parts)
    if n == 0:
        return None
    for i in range(1, n):
        feature_parts = parts[:i]
        feature = ".".join(feature_parts)
        attribute_parts = parts[i:]
        attribute = ".".join(attribute_parts)
        if is_valid_feature(model, feature) and is_valid_attribute(model, attribute):
            return (feature, attribute)
    return None


def is_feature_ancestor(feature: Feature, possible_ancestor: Feature) -> bool:
    """Check if possible_ancestor is an ancestor of feature in the feature tree."""
    parent = feature.parent
    while parent is not None:
        if parent == possible_ancestor:
            return True
        parent = parent.parent
    return False


def get_subtree(feature: Feature) -> list[Feature]:
    """Get all features in the subtree rooted at feature (including itself)."""
    subtree = [feature]
    for relation in feature.get_relations():
        for child in relation.children:
            subtree.extend(get_subtree(child))
    return subtree
