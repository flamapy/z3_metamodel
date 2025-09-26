import itertools
import copy
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
    FeatureType
)

from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.fm_metamodel.transformations import FlatFM
from flamapy.metamodels.fm_metamodel.transformations.refactorings import (
    FeatureCardinalityRefactoring
)
from flamapy.metamodels.fm_metamodel.transformations import FMSecureFeaturesNames


LOGGER = logging.getLogger('FmToZ3')


class FmToZ3(ModelToModel):

    @staticmethod
    def get_source_extension() -> str:
        return "fm"

    @staticmethod
    def get_destination_extension() -> str:
        return "z3"

    def __init__(self, source_model: FeatureModel) -> None:
        self.source_model = source_model
        self.destination_model: Optional[Z3Model] = None
        self._counter: int = 0

    def transform(self) -> Z3Model:
        # FlatFM if the feature model contains imports
        feature_model = self.source_model
        if feature_model.imports:
            feature_model = FlatFM(feature_model).transform()
        # Apply the feature cardinality refactoring to the source model
        if FeatureCardinalityRefactoring(feature_model).is_applicable():
            feature_model = copy.deepcopy(feature_model)
            feature_model = FeatureCardinalityRefactoring(feature_model).transform()
        self.source_model = feature_model

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
        formula = (self.destination_model.get_variable(root_feature.name).sel)
        self.destination_model.add_constraint(formula)
        features = [root_feature]
        while features:
            feature = features.pop()
            for relation in feature.get_relations():
                self._add_relation_formula(relation)
                features.extend(relation.children)
        
    def _traverse_constraints(self) -> None:
        for constraint in self.source_model.get_constraints():
            self._add_constraint_formula(constraint)

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
        parent = self.destination_model.get_variable(relation.parent.name).sel
        child = self.destination_model.get_variable(relation.children[0].name).sel
        formula = (parent == child)
        self.destination_model.add_constraint(formula)

    def _add_optional_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_variable(relation.parent.name).sel
        child = self.destination_model.get_variable(relation.children[0].name).sel
        formula = z3.Implies(child, parent)
        self.destination_model.add_constraint(formula)

    def _add_or_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_variable(relation.parent.name).sel
        children = [self.destination_model.get_variable(child.name).sel
                    for child in relation.children]
        formula = (parent == z3.Or(*children))
        self.destination_model.add_constraint(formula)

    def _add_alternative_formula(self, relation: Relation) -> None:
        formulas = []
        parent = self.destination_model.get_variable(relation.parent.name).sel
        children = [self.destination_model.get_variable(child.name).sel
                    for child in relation.children]
        for child in children:
            children_negatives = set(children) - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        self.destination_model.add_constraint(formula)

    def _add_mutex_formula(self, relation: Relation) -> None:
        formulas = []
        parent = self.destination_model.get_variable(relation.parent.name).sel
        children = {self.destination_model.get_variable(child.name).sel
                    for child in relation.children}
        for child in children:
            children_negatives = children - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        formula = z3.Or(parent == z3.Not(z3.Or(*children)), formula)
        self.destination_model.add_constraint(formula)

    def _add_cardinality_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_variable(relation.parent.name).sel
        children = {self.destination_model.get_variable(child.name).sel
                    for child in relation.children}
        or_ctc = []
        for k in range(relation.card_min, relation.card_max + 1):
            combi_k = list(itertools.combinations(children, k))
            for positives in combi_k:
                negatives = children - set(positives)
                if positives:
                    positives_and_ctc = z3.And(*positives)
                if negatives:
                    negatives_and_ctc = z3.And([z3.Not(ch) for ch in negatives])
                if positives and negatives:
                    and_ctc = z3.And(positives_and_ctc, negatives_and_ctc)
                elif positives:
                    and_ctc = positives_and_ctc
                elif negatives: 
                    and_ctc = negatives_and_ctc
                or_ctc.append(and_ctc) 
        formula_or_ctc = z3.Or(*or_ctc)
        formula = (parent == formula_or_ctc)
        self.destination_model.add_constraint(formula)

    def _add_constraint_formula(self, ctc: Constraint) -> None:
        expr  = self._get_expression(ctc.ast.root, None)
        self.destination_model.add_constraint(expr)

    def _get_expression(self, node: Node, parent: Node) -> z3.ExprRef:
        if node.is_term():
            if parent is None:  # process terminal node as boolean feature
                if isinstance(node.data, str):
                    expr = self.destination_model.get_variable(node.data)
                    if expr is None:
                        raise FlamaException(f'Unsupported feature: {node.data}')
                else:
                    raise FlamaException(f'Unsupported terminal feature: {type(node.data)}')
            else:
                # process terminal node according to the parent
                if isinstance(node.data, str):
                    variable = self.destination_model.get_variable(node.data)
                    if variable is not None:  # is a feature
                        if parent.data in LOGICAL_OPERATORS:
                            expr = variable.sel
                        elif parent.data in ARITHMETIC_OPERATORS:
                            expr = variable.val
                        elif parent.data in AGGREGATION_OPERATORS:
                            expr = variable  # the aggregation operator will handle it
                        else:
                            raise FlamaException(f'Unsupported operator: {parent.data}')
                    else:  # is not a feature, so it may be an attribute
                        if '.' in node.data:  # attribute of a feature
                            feature_name, attr_name = find_feature_and_attribute(self.destination_model, node.data)
                            feature_info = self.destination_model.get_variable(feature_name)
                            attribute_info = feature_info.attributes.get(attr_name, None)
                            if attribute_info is not None:
                                expr = attribute_info['var']
                            else:
                                attribute = self.source_model.get_attribute_by_name(attr_name)
                                if attribute is not None:
                                    expr = self.destination_model.add_attribute(feature_name, 
                                                                                attr_name, 
                                                                                attribute.attribute_type, 
                                                                                None)
                                else:
                                    expr = node.data
                        else:
                            expr = node.data
                            # if feature_info is None:
                            #     raise FlamaException(f'Unsupported feature in attribute: {feature_name}')
                            # attr_info = feature_info.attributes.get(attr_name, None)
                            # if attr_info is None:
                            #     raise FlamaException(f'Unsupported attribute: {attr_name} in feature {feature_name}')
                            # expr = attr_info['var']
                        #TODO: se debe guardar una referencia al atributo (no str).
                        # attribute_var = self.destination_model.attributes.get(node.data, None)
                        # if attribute_var is not None:
                        #     expr = attribute_var
                        # else:  # is a string or boolean constant
                else:
                    expr = node.data
        else:  # is operation
            if node.is_binary_op():
                left_expr = self._get_expression(node.left, node)
                right_expr = self._get_expression(node.right, node)
                if node.data == ASTOperation.AND:
                    expr = z3.And(left_expr, right_expr)
                elif node.data == ASTOperation.OR:
                    expr = z3.Or(left_expr, right_expr)
                elif node.data in [ASTOperation.IMPLIES, ASTOperation.REQUIRES]:
                    expr = z3.Implies(left_expr, right_expr)
                elif node.data == ASTOperation.EXCLUDES:
                    expr = z3.Implies(left_expr, z3.Not(right_expr))
                elif node.data == ASTOperation.XOR:
                    expr = z3.Xor(left_expr, right_expr)
                elif node.data == ASTOperation.EQUIVALENCE:
                    expr = (left_expr == right_expr)
                elif node.data == ASTOperation.ADD:
                    expr = (left_expr + right_expr)
                elif node.data == ASTOperation.SUB:
                    expr = (left_expr - right_expr)
                elif node.data == ASTOperation.MUL:
                    expr = (left_expr * right_expr)
                elif node.data == ASTOperation.DIV:
                    expr = (left_expr / right_expr)
                elif node.data == ASTOperation.EQUALS:
                    expr = (left_expr == right_expr)
                elif node.data == ASTOperation.LOWER:
                    expr = (left_expr < right_expr)
                elif node.data == ASTOperation.GREATER:
                    expr = (left_expr > right_expr)
                elif node.data == ASTOperation.LOWER_EQUALS:
                    expr = (left_expr <= right_expr)
                elif node.data == ASTOperation.GREATER_EQUALS:
                    expr = (left_expr >= right_expr)
                elif node.data == ASTOperation.NOT_EQUALS:
                    expr = (left_expr != right_expr)
                else:
                    raise FlamaException(f'Unsupported binary operator: {node.data}')
            elif node.is_unary_op():
                left_expr = self._get_expression(node.left, node)
                if node.data == ASTOperation.NOT:
                    expr = z3.Not(left_expr)
                else:
                    raise FlamaException(f'Unsupported unary operator: {node.data}')
            elif node.is_aggregate_op():
                left_expr = self._get_expression(node.left, node)
                right_expr = self._get_expression(node.right, node) if node.right is not None else None
                if node.data in [ASTOperation.SUM, ASTOperation.AVG]:
                    # TODO: check if aggregate functions can be applied over features too
                    # Obtain the list of attribute variables to aggregate
                    attributes_vars = self.destination_model.attributes.get(left_expr, None)
                    if right_expr is not None:  # consider only the feature subtree
                        attributes_vars = []
                        feature = self.source_model.get_feature_by_name(right_expr.name)
                        for feat in get_subtree(feature):
                            feature_attributes = self.destination_model.get_variable(feat.name).attributes
                            if left_expr in feature_attributes:
                                attributes_vars.append(feature_attributes[left_expr]['var'])
                    if node.data == ASTOperation.SUM:
                        expr = z3.Sum(attributes_vars)
                    elif node.data == ASTOperation.AVG:
                        expr = z3.Sum(attributes_vars) / len(attributes_vars)
                #elif node.data in [ASTOperation.LEN]:
                else:
                    raise FlamaException(f'Unsupported aggregation operator: {node.data}')
        return expr


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