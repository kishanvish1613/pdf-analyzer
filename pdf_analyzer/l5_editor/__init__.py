"""
L5 Dimension Editor Package.
Pure Python representations, SnapIndex, DimensionLane, LabelPlacer, and Gate G7.
"""

from pdf_analyzer.l5_editor.snap_index import SnapIndexEngine, SnapIndex, SnapTarget, SnapQueryResult
from pdf_analyzer.l5_editor.dimension_lane import (
    DimensionLaneEngine,
    DimensionArrow,
    ExtensionLine,
    DimensionLaneModel,
)
from pdf_analyzer.l5_editor.label_placer import (
    LabelPlacerEngine,
    LabelAnchor,
    PlacedLabel,
)
from pdf_analyzer.l5_editor.model import (
    EditorGuide,
    UnownedGuide,
    EditorPageModel,
    EditorModelBuilder,
)
from pdf_analyzer.l5_editor.gate_g7 import (
    GateG7Evaluator,
    GateG7Report,
    ArrowEndpointCheck,
)

__all__ = [
    "SnapIndexEngine",
    "SnapIndex",
    "SnapTarget",
    "SnapQueryResult",
    "DimensionLaneEngine",
    "DimensionArrow",
    "ExtensionLine",
    "DimensionLaneModel",
    "LabelPlacerEngine",
    "LabelAnchor",
    "PlacedLabel",
    "EditorGuide",
    "UnownedGuide",
    "EditorPageModel",
    "EditorModelBuilder",
    "GateG7Evaluator",
    "GateG7Report",
    "ArrowEndpointCheck",
]

