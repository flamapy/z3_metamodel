"""Backward-compatible re-export.

``AttributeOptimization`` and ``OptimizationGoal`` now live in the core framework so
that every backend shares one interface. This module keeps the historical import path
``flamapy.metamodels.z3_metamodel.operations.interfaces.attribute_optimization`` working.
"""
from flamapy.core.operations.attribute_optimization import (
    AttributeOptimization,
    OptimizationGoal,
)

__all__ = ["AttributeOptimization", "OptimizationGoal"]
