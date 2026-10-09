"""
L5 SnapIndex Engine (E7, E10).
Extracts sub-pixel snap targets directly from L0 ByteLayer and L2 RuleSets:
- Rule centres, painted inner/outer edges
- Box edges and container boundaries
- Text ink-box edges and baselines
- Page CropBox edges
Provides indexed, priority-ordered snapping for interactive guide editing.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Set

from pdf_analyzer.l0_bytes.primitives import PageByteLayer, PaintedTextChar
from pdf_analyzer.l2_primitives.ruleset import RuleSet, Rule
from pdf_analyzer.l3_topology.containers import Container
from pdf_analyzer.l3_topology.table_grid import TableGrid


@dataclass
class SnapTarget:
    target_id: str
    axis: str  # 'X' (vertical guide) | 'Y' (horizontal guide)
    coord_pt: float
    start_pt: float
    end_pt: float
    target_type: str  # 'rule_centre' | 'rule_outer' | 'rule_inner' | 'box_edge' | 'ink_edge' | 'baseline' | 'page_edge'
    owner_id: str
    description: str
    priority: int = 1  # 1 (highest: rules) to 5 (lowest: ink bounding edges)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "axis": self.axis,
            "coord_pt": self.coord_pt,
            "start_pt": self.start_pt,
            "end_pt": self.end_pt,
            "target_type": self.target_type,
            "owner_id": self.owner_id,
            "description": self.description,
            "priority": self.priority,
            # Backwards compatibility keys
            "position_pt": self.coord_pt,
            "type": self.target_type,
        }


@dataclass
class SnapQueryResult:
    target: SnapTarget
    snapped_coord_pt: float
    delta_pt: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "snapped_coord_pt": self.snapped_coord_pt,
            "delta_pt": self.delta_pt,
            "description": self.description,
        }


class SnapIndex:
    def __init__(self, targets: Optional[List[SnapTarget]] = None):
        self.targets: List[SnapTarget] = list(targets or [])
        self.targets_x: List[SnapTarget] = sorted(
            [t for t in self.targets if t.axis == "X"],
            key=lambda t: (t.coord_pt, t.priority),
        )
        self.targets_y: List[SnapTarget] = sorted(
            [t for t in self.targets if t.axis == "Y"],
            key=lambda t: (t.coord_pt, t.priority),
        )

    def add_target(self, target: SnapTarget) -> None:
        self.targets.append(target)
        if target.axis == "X":
            self.targets_x.append(target)
            self.targets_x.sort(key=lambda t: (t.coord_pt, t.priority))
        else:
            self.targets_y.append(target)
            self.targets_y.sort(key=lambda t: (t.coord_pt, t.priority))

    def query(
        self,
        axis: str,
        coord_pt: float,
        tolerance_pt: float = 3.0,
        span_interval: Optional[Tuple[float, float]] = None,
        target_types: Optional[Set[str]] = None,
    ) -> Optional[SnapQueryResult]:
        """
        Finds the closest snap target on the given axis within tolerance.
        Prioritizes closer distance, then higher priority target type.
        """
        candidates = self.targets_x if axis.upper() == "X" else self.targets_y
        best_target: Optional[SnapTarget] = None
        best_dist: float = float("inf")
        best_priority: int = 999

        for t in candidates:
            if target_types and t.target_type not in target_types:
                continue

            # Check overlap along span if span_interval provided
            if span_interval is not None:
                s_min, s_max = min(span_interval), max(span_interval)
                t_min, t_max = min(t.start_pt, t.end_pt), max(t.start_pt, t.end_pt)
                if s_max < t_min - tolerance_pt or s_min > t_max + tolerance_pt:
                    continue

            dist = abs(t.coord_pt - coord_pt)
            if dist <= tolerance_pt:
                if dist < best_dist - 1e-4 or (abs(dist - best_dist) <= 1e-4 and t.priority < best_priority):
                    best_dist = dist
                    best_target = t
                    best_priority = t.priority

        if best_target is not None:
            return SnapQueryResult(
                target=best_target,
                snapped_coord_pt=best_target.coord_pt,
                delta_pt=best_target.coord_pt - coord_pt,
                description=best_target.description,
            )
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "targets_count": len(self.targets),
            "targets_x_count": len(self.targets_x),
            "targets_y_count": len(self.targets_y),
            "targets": [t.to_dict() for t in self.targets],
        }


class SnapIndexEngine:
    """
    Builds a vector-accurate SnapIndex from L0 ByteLayer primitives and L2/L3 topology.
    """

    def build_snap_index(
        self,
        page_layer: PageByteLayer,
        ruleset: Optional[RuleSet] = None,
        containers: Optional[List[Container]] = None,
        table_grid: Optional[TableGrid] = None,
    ) -> List[SnapTarget]:
        targets: List[SnapTarget] = []
        cb = page_layer.cropbox_pt
        c_x0, c_y0, c_x1, c_y1 = cb

        # 1. Page CropBox Edges (Priority 2)
        targets.append(
            SnapTarget(
                target_id="page_left",
                axis="X",
                coord_pt=c_x0,
                start_pt=c_y0,
                end_pt=c_y1,
                target_type="page_edge",
                owner_id="page",
                description=f"Page left edge, x = {c_x0:.3f} pt",
                priority=2,
            )
        )
        targets.append(
            SnapTarget(
                target_id="page_right",
                axis="X",
                coord_pt=c_x1,
                start_pt=c_y0,
                end_pt=c_y1,
                target_type="page_edge",
                owner_id="page",
                description=f"Page right edge, x = {c_x1:.3f} pt",
                priority=2,
            )
        )
        targets.append(
            SnapTarget(
                target_id="page_top",
                axis="Y",
                coord_pt=c_y1,
                start_pt=c_x0,
                end_pt=c_x1,
                target_type="page_edge",
                owner_id="page",
                description=f"Page top edge, y = {c_y1:.3f} pt",
                priority=2,
            )
        )
        targets.append(
            SnapTarget(
                target_id="page_bottom",
                axis="Y",
                coord_pt=c_y0,
                start_pt=c_x0,
                end_pt=c_x1,
                target_type="page_edge",
                owner_id="page",
                description=f"Page bottom edge, y = {c_y0:.3f} pt",
                priority=2,
            )
        )

        # 2. RuleSet Rules (Priority 1)
        if ruleset:
            for rule in ruleset.rules:
                if rule.orientation == "V":
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_centre",
                            axis="X",
                            coord_pt=rule.centre,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_centre",
                            owner_id=rule.id,
                            description=f"{rule.id} centre, x = {rule.centre:.3f} pt",
                            priority=1,
                        )
                    )
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_outer",
                            axis="X",
                            coord_pt=rule.painted_outer,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_outer",
                            owner_id=rule.id,
                            description=f"{rule.id} outer edge, x = {rule.painted_outer:.3f} pt",
                            priority=1,
                        )
                    )
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_inner",
                            axis="X",
                            coord_pt=rule.painted_inner,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_inner",
                            owner_id=rule.id,
                            description=f"{rule.id} inner edge, x = {rule.painted_inner:.3f} pt",
                            priority=1,
                        )
                    )
                else:  # 'H'
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_centre",
                            axis="Y",
                            coord_pt=rule.centre,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_centre",
                            owner_id=rule.id,
                            description=f"{rule.id} centre, y = {rule.centre:.3f} pt",
                            priority=1,
                        )
                    )
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_outer",
                            axis="Y",
                            coord_pt=rule.painted_outer,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_outer",
                            owner_id=rule.id,
                            description=f"{rule.id} outer edge, y = {rule.painted_outer:.3f} pt",
                            priority=1,
                        )
                    )
                    targets.append(
                        SnapTarget(
                            target_id=f"{rule.id}_inner",
                            axis="Y",
                            coord_pt=rule.painted_inner,
                            start_pt=rule.start,
                            end_pt=rule.end,
                            target_type="rule_inner",
                            owner_id=rule.id,
                            description=f"{rule.id} inner edge, y = {rule.painted_inner:.3f} pt",
                            priority=1,
                        )
                    )

        # 3. Containers / Box Edges (Priority 2)
        if containers:
            for cont in containers:
                bx0, by0, bx1, by1 = cont.bbox_pt
                targets.append(
                    SnapTarget(
                        target_id=f"{cont.id}_left",
                        axis="X",
                        coord_pt=bx0,
                        start_pt=by0,
                        end_pt=by1,
                        target_type="box_edge",
                        owner_id=cont.id,
                        description=f"{cont.id} left edge, x = {bx0:.3f} pt",
                        priority=2,
                    )
                )
                targets.append(
                    SnapTarget(
                        target_id=f"{cont.id}_right",
                        axis="X",
                        coord_pt=bx1,
                        start_pt=by0,
                        end_pt=by1,
                        target_type="box_edge",
                        owner_id=cont.id,
                        description=f"{cont.id} right edge, x = {bx1:.3f} pt",
                        priority=2,
                    )
                )
                targets.append(
                    SnapTarget(
                        target_id=f"{cont.id}_top",
                        axis="Y",
                        coord_pt=by1,
                        start_pt=bx0,
                        end_pt=bx1,
                        target_type="box_edge",
                        owner_id=cont.id,
                        description=f"{cont.id} top edge, y = {by1:.3f} pt",
                        priority=2,
                    )
                )
                targets.append(
                    SnapTarget(
                        target_id=f"{cont.id}_bottom",
                        axis="Y",
                        coord_pt=by0,
                        start_pt=bx0,
                        end_pt=bx1,
                        target_type="box_edge",
                        owner_id=cont.id,
                        description=f"{cont.id} bottom edge, y = {by0:.3f} pt",
                        priority=2,
                    )
                )

        # 4. Text baselines & ink-box edges (Priority 3 & 4)
        seen_baselines: Set[float] = set()
        chars = getattr(page_layer, "chars", getattr(page_layer, "text_chars", []))
        for ch in chars:
            bl = round(ch.baseline_y, 2)
            if bl not in seen_baselines:
                seen_baselines.add(bl)
                targets.append(
                    SnapTarget(
                        target_id=f"baseline_{bl:.2f}",
                        axis="Y",
                        coord_pt=ch.baseline_y,
                        start_pt=c_x0,
                        end_pt=c_x1,
                        target_type="baseline",
                        owner_id=f"text_line_{bl:.2f}",
                        description=f"Baseline y = {ch.baseline_y:.3f} pt",
                        priority=3,
                    )
                )

        return targets
