"""
Synthetic statement ground truth generator and test suite.
"""

from tests.synthetic.generators import (
    GroundTruthSpec,
    KnownLine,
    KnownRect,
    KnownText,
    KnownColumn,
    KnownRow,
    create_full_grid_synthetic_statement,
    create_unruled_synthetic_statement,
)

__all__ = [
    "GroundTruthSpec",
    "KnownLine",
    "KnownRect",
    "KnownText",
    "KnownColumn",
    "KnownRow",
    "create_full_grid_synthetic_statement",
    "create_unruled_synthetic_statement",
]

