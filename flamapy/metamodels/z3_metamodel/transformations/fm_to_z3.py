import re
import itertools
from typing import Optional

import z3

from flamapy.core.models.ast import AST, ASTOperation
from flamapy.core.transformations import ModelToModel
from flamapy.metamodels.fm_metamodel.models import FeatureModel
from flamapy.metamodels.fm_metamodel.models import FeatureModel, Feature, Relation, Constraint
from flamapy.metamodels.z3_metamodel.models import Z3Model
from flamapy.metamodels.bdd_metamodel.transformations.fm_to_bdd_pl import FmToBDD as FmToBddPL
from flamapy.metamodels.bdd_metamodel.transformations.fm_to_bdd_cnf import FmToBDD as FmToBddCNF


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
        self.destination_model = Z3Model()
        self._declare_features()
        self._traverse_feature_tree()
        self._traverse_constraints()
        return self.destination_model

    def _declare_features(self) -> None:
        assert self.destination_model is not None, "destination_model is None"
        for feature in self.source_model.get_features():
            if not self.destination_model.has_variable(feature.name):
                self.destination_model.add_variable(feature.name, feature.feature_type)
                self._counter += 1

    def _traverse_feature_tree(self) -> None:
        """Traverse the feature tree from the root and return the list of formulas."""
        if self.source_model is None or self.source_model.root is None:
            return []
        assert self.destination_model is not None, "destination_model is None"
        # The root is always present
        root_feature = self.source_model.root
        formula = (self.destination_model.get_boolean_variable(root_feature.name))
        self.destination_model.add_formula(formula)
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
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        child = self.destination_model.get_boolean_variable(relation.children[0].name)
        formula = (parent == child)
        self.destination_model.add_formula(formula)

    def _add_optional_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        child = self.destination_model.get_boolean_variable(relation.children[0].name)
        formula = z3.Implies(child, parent)
        self.destination_model.add_formula(formula)

    def _add_or_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        children = [self.destination_model.get_boolean_variable(child.name) 
                    for child in relation.children]
        formula = (parent == z3.Or(*children))
        self.destination_model.add_formula(formula)

    def _add_alternative_formula(self, relation: Relation) -> None:
        formulas = []
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        children = [self.destination_model.get_boolean_variable(child.name)
                    for child in relation.children]
        for child in children:
            children_negatives = set(children) - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        self.destination_model.add_formula(formula)

    def _add_mutex_formula(self, relation: Relation) -> None:
        formulas = []
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        children = {self.destination_model.get_boolean_variable(child.name)
                    for child in relation.children}
        for child in children:
            children_negatives = children - {child}
            formula = (child == z3.And([z3.Not(ch) for ch in children_negatives] + [parent]))
            formulas.append(formula)
        formula = z3.And(*formulas)
        formula = z3.Or(parent == z3.Not(z3.Or(*children)), formula)
        self.destination_model.add_formula(formula)

    def _add_cardinality_formula(self, relation: Relation) -> None:
        parent = self.destination_model.get_boolean_variable(relation.parent.name)
        children = {self.destination_model.get_boolean_variable(child.name)
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
        self.destination_model.add_formula(formula)

    def _add_constraint_formula(self, ctc: Constraint) -> None:
        if ctc.is_logical_constraint():
            expr = self._get_logical_expression(ctc.ast)
        elif ctc.is_arithmetic_constraint():
            expr = self._get_arithmetic_expression(ctc.ast)
        else:
            raise ValueError(f"Unknown constraint type: {ctc.type}")
        return expr

    def _get_logical_expression(self, ast: AST) -> z3.ExprRef:

    def _get_arithmetic_expression(self, ast: AST) -> z3.ExprRef:
        if ast.root.is_term():
            if self.destination_model.get_boolean_variable(ast.root.data)
            self.destination_model.add_formula()

    def _add_constraint_formula(self, ctc: Constraint) -> None:

        constraint_str = re.sub(rf"\b{ASTOperation.XOR.value}\b", 
                                BDDModel.LogicConnective.XOR.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.NOT.value}\b", 
                                BDDModel.LogicConnective.NOT.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.AND.value}\b", 
                                BDDModel.LogicConnective.AND.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.OR.value}\b", 
                                BDDModel.LogicConnective.OR.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.IMPLIES.value}\b", 
                                BDDModel.LogicConnective.IMPLIES.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.EQUIVALENCE.value}\b", 
                                BDDModel.LogicConnective.EQUIVALENCE.value, constraint_str)
        constraint_str = re.sub(rf"\b{ASTOperation.REQUIRES.value}\b", 
                                BDDModel.LogicConnective.IMPLIES.value, constraint_str)
        constraint_str = re.sub(
            rf"\b{ASTOperation.EXCLUDES.value}\b",
            f'{BDDModel.LogicConnective.IMPLIES.value} {BDDModel.LogicConnective.NOT.value}',
            constraint_str
        )
        return constraint_str