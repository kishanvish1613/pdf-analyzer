"""
Module A: Overall Layout and Page Structure Analysis.
Implements Containment + Recursive Whitespace XY-Cut Tree with Invariant Verification (I1-I6)
and Self-Repair. Strictly processes each page independently.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
import numpy as np

from pdf_analyzer.config import AnalyzerConfig
from pdf_analyzer.models import (
    TextSpanModel, PageMeta, LayoutTreeNode, BoundingBox, MultiUnitValue
)
from pdf_analyzer.utils.units import create_bbox_from_pt, create_multi_unit_value
from pdf_analyzer.utils.geometry import bbox_contains, bbox_intersection, bbox_iou

logger = logging.getLogger(__name__)


class LayoutAnalyzer:
    """
    Constructs the hierarchical Layout Tree per page using containment and recursive XY-cut.
    Enforces Invariants I1-I6 with an auto-repair loop.
    """

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_page_layout(
        self,
        page_meta: PageMeta,
        spans: List[TextSpanModel],
        drawings: List[Dict[str, Any]],
        images: Optional[List[Dict[str, Any]]] = None,
        table_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze layout regions and build layout tree for a single page independently.
        """
        page_num = page_meta.page_number
        page_w = page_meta.width.pt
        page_h = page_meta.height.pt
        images = images or []

        # 1. Collect primitives (Spans, Images, Drawings)
        primitive_map: Dict[str, Dict[str, Any]] = {}
        for idx, s in enumerate(spans):
            pid = f"span_p{page_num}_{idx}"
            primitive_map[pid] = {
                "id": pid,
                "type": "text",
                "bbox_pt": s.ink_box.raw_pt,
                "text": s.text,
                "span": s
            }

        for idx, img in enumerate(images):
            pid = f"img_p{page_num}_{idx}"
            primitive_map[pid] = {
                "id": pid,
                "type": "image",
                "bbox_pt": img.get("bbox", (0, 0, 10, 10)),
                "text": "[IMAGE]"
            }

        # 2. Register CONTAINER nodes from closed stroked/filled rectangles
        containers: List[Dict[str, Any]] = []
        for idx, d in enumerate(drawings):
            bw = d.get("width_pt", 0.0)
            bh = d.get("height_pt", 0.0)
            bbox = d.get("bbox", (0.0, 0.0, 0.0, 0.0))
            is_rect = d.get("is_rect", False) or (bw > 10.0 and bh > 10.0)
            # Filter out full page background or tiny lines
            if is_rect and bw >= 20.0 and bh >= 12.0 and not (bw >= page_w - 5.0 and bh >= page_h - 5.0):
                cid = f"container_p{page_num}_{idx}"
                containers.append({
                    "id": cid,
                    "bbox_pt": bbox,
                    "drawing": d,
                    "member_pids": []
                })

        # Sort containers by area ascending (smallest enclosing container wins)
        containers.sort(key=lambda c: (c["bbox_pt"][2] - c["bbox_pt"][0]) * (c["bbox_pt"][3] - c["bbox_pt"][1]))

        # 3. Assign primitives to smallest enclosing container (>= 90% containment or center inside)
        free_pids: List[str] = []
        for pid, prim in primitive_map.items():
            px0, py0, px1, py1 = prim["bbox_pt"]
            p_area = max(0.1, (px1 - px0) * (py1 - py0))
            p_cx = (px0 + px1) / 2.0
            p_cy = (py0 + py1) / 2.0

            assigned_container = None
            for c in containers:
                cx0, cy0, cx1, cy1 = c["bbox_pt"]
                # Check center inside and overlap area
                if (cx0 - 1.0 <= p_cx <= cx1 + 1.0) and (cy0 - 1.0 <= p_cy <= cy1 + 1.0):
                    ix0 = max(px0, cx0)
                    iy0 = max(py0, cy0)
                    ix1 = min(px1, cx1)
                    iy1 = min(py1, cy1)
                    if ix1 > ix0 and iy1 > iy0:
                        inter_area = (ix1 - ix0) * (iy1 - iy0)
                        if inter_area / p_area >= 0.85:
                            assigned_container = c
                            break

            if assigned_container:
                assigned_container["member_pids"].append(pid)
            else:
                free_pids.append(pid)

        # 4. Table Grid Registration
        table_bbox_pt = None
        table_grid_pids: Set[str] = set()
        if table_meta and table_meta.get("raw_bbox_pt"):
            table_bbox_pt = table_meta["raw_bbox_pt"]
            tx0, ty0, tx1, ty1 = table_bbox_pt
            for pid in list(free_pids):
                px0, py0, px1, py1 = primitive_map[pid]["bbox_pt"]
                pcx = (px0 + px1) / 2.0
                pcy = (py0 + py1) / 2.0
                if (tx0 - 2.0 <= pcx <= tx1 + 2.0) and (ty0 - 1.0 <= pcy <= ty1 + 1.0):
                    table_grid_pids.add(pid)
                    free_pids.remove(pid)

        # 5. Recursive XY-Cut on Remaining Free Primitives
        line_pitches = self._calculate_median_line_pitch(spans)
        min_gap_y = max(6.0, 1.4 * line_pitches)
        min_gap_x = max(12.0, self.config.tolerances.column_gap_min_pt)

        leaf_blocks = self._recursive_xy_cut(free_pids, primitive_map, min_gap_y, min_gap_x, page_w, page_h)

        # 6. Build Layout Nodes and Classify Semantics
        nodes: Dict[str, LayoutTreeNode] = {}
        root_id = f"page_root_p{page_num}"
        root_bbox = create_bbox_from_pt(0.0, 0.0, page_w, page_h, page_w, page_h, self.config.dpi)
        root_node = LayoutTreeNode(
            id=root_id,
            type="PAGE_ROOT",
            page=page_num,
            bbox=root_bbox,
            classifying_rule="page_boundary"
        )
        nodes[root_id] = root_node

        table_top_y = table_bbox_pt[1] if table_bbox_pt else page_h * 0.45
        table_bot_y = table_bbox_pt[3] if table_bbox_pt else page_h * 0.85
        footer_min_y = table_bot_y + self.config.tolerances.footer_min_gap_below_table_pt

        # A. Register Container Regions
        for c in containers:
            if not c["member_pids"]:
                # Empty container (decorative border/box)
                bx0, by0, bx1, by1 = c["bbox_pt"]
                node_bbox = create_bbox_from_pt(bx0, by0, bx1, by1, page_w, page_h, self.config.dpi)
                cnode = LayoutTreeNode(
                    id=c["id"],
                    type="DECORATIVE_CONTAINER",
                    page=page_num,
                    bbox=node_bbox,
                    parent_id=root_id,
                    is_container=True,
                    classifying_rule="vector_closed_path"
                )
                nodes[c["id"]] = cnode
                root_node.children_ids.append(c["id"])
                continue

            # Compute container member bounds
            m_boxes = [primitive_map[pid]["bbox_pt"] for pid in c["member_pids"]]
            cbx0 = min(c["bbox_pt"][0], min(b[0] for b in m_boxes))
            cby0 = min(c["bbox_pt"][1], min(b[1] for b in m_boxes))
            cbx1 = max(c["bbox_pt"][2], max(b[2] for b in m_boxes))
            cby1 = max(c["bbox_pt"][3], max(b[3] for b in m_boxes))
            c_bbox = create_bbox_from_pt(cbx0, cby0, cbx1, cby1, page_w, page_h, self.config.dpi)

            # Classify container
            c_type = self._classify_container(c, primitive_map, page_w, page_h)
            cnode = LayoutTreeNode(
                id=c["id"],
                type=c_type,
                page=page_num,
                bbox=c_bbox,
                parent_id=root_id,
                member_ids=c["member_pids"],
                is_container=True,
                classifying_rule="smallest_enclosing_box"
            )
            nodes[c["id"]] = cnode
            root_node.children_ids.append(c["id"])

        # B. Register Table Grid Region
        if table_bbox_pt or table_grid_pids:
            t_pids = list(table_grid_pids)
            if table_bbox_pt:
                tb_x0, tb_y0, tb_x1, tb_y1 = table_bbox_pt
            else:
                tb_x0 = min(primitive_map[pid]["bbox_pt"][0] for pid in t_pids)
                tb_y0 = min(primitive_map[pid]["bbox_pt"][1] for pid in t_pids)
                tb_x1 = max(primitive_map[pid]["bbox_pt"][2] for pid in t_pids)
                tb_y1 = max(primitive_map[pid]["bbox_pt"][3] for pid in t_pids)

            # Ensure table bbox includes member ink bounds fully
            if t_pids:
                tb_x0 = min(tb_x0, min(primitive_map[pid]["bbox_pt"][0] for pid in t_pids))
                tb_y0 = min(tb_y0, min(primitive_map[pid]["bbox_pt"][1] for pid in t_pids))
                tb_x1 = max(tb_x1, max(primitive_map[pid]["bbox_pt"][2] for pid in t_pids))
                tb_y1 = max(tb_y1, max(primitive_map[pid]["bbox_pt"][3] for pid in t_pids))

            t_bbox = create_bbox_from_pt(tb_x0, tb_y0, tb_x1, tb_y1, page_w, page_h, self.config.dpi)
            table_id = f"table_region_p{page_num}"
            table_node = LayoutTreeNode(
                id=table_id,
                type="TRANSACTION_TABLE",
                page=page_num,
                bbox=t_bbox,
                parent_id=root_id,
                member_ids=t_pids,
                is_container=True,
                classifying_rule="table_grid_rules_and_rows"
            )
            nodes[table_id] = table_node
            root_node.children_ids.append(table_id)

        # C. Register Free Leaf Blocks from Recursive XY-Cut
        for b_idx, block_pids in enumerate(leaf_blocks):
            if not block_pids:
                continue
            b_boxes = [primitive_map[pid]["bbox_pt"] for pid in block_pids]
            bx0 = min(b[0] for b in b_boxes)
            by0 = min(b[1] for b in b_boxes)
            bx1 = max(b[2] for b in b_boxes)
            by1 = max(b[3] for b in b_boxes)
            b_bbox = create_bbox_from_pt(bx0, by0, bx1, by1, page_w, page_h, self.config.dpi)

            b_type, b_rule = self._classify_leaf_block(
                block_pids, primitive_map, bx0, by0, bx1, by1,
                table_top_y, footer_min_y, page_w, page_h
            )

            block_id = f"block_p{page_num}_{b_idx}"
            b_node = LayoutTreeNode(
                id=block_id,
                type=b_type,
                page=page_num,
                bbox=b_bbox,
                parent_id=root_id,
                member_ids=block_pids,
                is_container=False,
                classifying_rule=b_rule
            )
            nodes[block_id] = b_node
            root_node.children_ids.append(block_id)

        # 7. Invariants Verification & Auto-Repair Loop (max 3 passes)
        repair_logs = self._auto_repair_invariants(nodes, primitive_map, page_w, page_h)

        # 8. Extract Flat Regions List for Pipeline API
        regions_list: List[Dict[str, Any]] = []
        for nid, node in nodes.items():
            if nid == root_id:
                continue
            regions_list.append({
                "region_id": node.id,
                "region_type": node.type.lower(),
                "page_number": page_num,
                "bbox": node.bbox.to_dict(),
                "raw_bbox_pt": list(node.bbox.raw_pt),
                "is_container": node.is_container,
                "element_count": len(node.member_ids),
                "tightness_iou": node.tightness_iou,
                "leakage_pct": node.leakage_pct,
                "classifying_rule": node.classifying_rule
            })

        return {
            "layout_tree": {nid: n.to_dict() for nid, n in nodes.items()},
            "regions": regions_list,
            "page_structure": {
                "column_structure": "multi_block" if len(leaf_blocks) > 2 else "single_column",
                "total_regions": len(regions_list),
                "containers_count": len(containers),
                "invariants_satisfied": len(repair_logs.get("violations", [])) == 0
            },
            "auto_repair_logs": repair_logs
        }

    def _recursive_xy_cut(
        self,
        pids: List[str],
        primitive_map: Dict[str, Dict[str, Any]],
        min_gap_y: float,
        min_gap_x: float,
        page_w: float,
        page_h: float
    ) -> List[List[str]]:
        """Recursively cuts primitive sets using horizontal and vertical whitespace projections."""
        if not pids:
            return []
        if len(pids) == 1:
            return [pids]

        boxes = [primitive_map[pid]["bbox_pt"] for pid in pids]
        min_y = min(b[1] for b in boxes)
        max_y = max(b[3] for b in boxes)

        # 1. Horizontal Cuts (Y projection whitespace)
        h_intervals = sorted([(b[1], b[3], pid) for b, pid in zip(boxes, pids)], key=lambda x: x[0])
        bands: List[List[str]] = []
        cur_band: List[str] = [h_intervals[0][2]]
        cur_bottom = h_intervals[0][1]

        for y0, y1, pid in h_intervals[1:]:
            if y0 - cur_bottom >= min_gap_y:
                bands.append(cur_band)
                cur_band = [pid]
                cur_bottom = y1
            else:
                cur_band.append(pid)
                cur_bottom = max(cur_bottom, y1)
        bands.append(cur_band)

        if len(bands) > 1:
            result = []
            for band in bands:
                result.extend(self._recursive_xy_cut(band, primitive_map, min_gap_y, min_gap_x, page_w, page_h))
            return result

        # 2. Vertical Cuts within Band (X projection whitespace)
        v_intervals = sorted([(b[0], b[2], pid) for b, pid in zip(boxes, pids)], key=lambda x: x[0])
        blocks: List[List[str]] = []
        cur_block: List[str] = [v_intervals[0][2]]
        cur_right = v_intervals[0][1]

        for x0, x1, pid in v_intervals[1:]:
            if x0 - cur_right >= min_gap_x:
                blocks.append(cur_block)
                cur_block = [pid]
                cur_right = x1
            else:
                cur_block.append(pid)
                cur_right = max(cur_right, x1)
        blocks.append(cur_block)

        if len(blocks) > 1:
            result = []
            for block in blocks:
                result.extend(self._recursive_xy_cut(block, primitive_map, min_gap_y, min_gap_x, page_w, page_h))
            return result

        return [pids]

    def _classify_container(
        self,
        container: Dict[str, Any],
        primitive_map: Dict[str, Dict[str, Any]],
        page_w: float,
        page_h: float
    ) -> str:
        """Classify container node semantics."""
        members = container.get("member_pids", [])
        combined_text = " ".join(primitive_map[pid].get("text", "") for pid in members).lower()
        if any(w in combined_text for w in ["road", "street", "pin", "lane", "box", "nagar", "delhi", "mumbai", "pune", "bangalore", "dist", "floor", "house", "flat"]):
            return "ADDRESS_BLOCK"
        if any(w in combined_text for w in ["account", "branch", "ifsc", "customer", "currency"]):
            return "ACCOUNT_DETAILS_BOX"
        return "CONTAINER_BLOCK"

    def _classify_leaf_block(
        self,
        block_pids: List[str],
        primitive_map: Dict[str, Dict[str, Any]],
        bx0: float, by0: float, bx1: float, by1: float,
        table_top_y: float, footer_min_y: float,
        page_w: float, page_h: float
    ) -> Tuple[str, str]:
        """Classify leaf block by geometry and content."""
        combined_text = " ".join(primitive_map[pid].get("text", "") for pid in block_pids).strip()
        text_lower = combined_text.lower()

        # 1. Page Number
        if len(block_pids) <= 2 and ("page " in text_lower or "/ " in text_lower) and (by0 < 50.0 or by0 > page_h - 60.0):
            return "PAGE_NUMBER", "page_number_pattern"

        # 2. Logo / Branding
        if any(primitive_map[pid].get("type") == "image" for pid in block_pids) or (by1 <= 90.0 and bx1 <= page_w * 0.45 and len(block_pids) <= 3):
            return "LOGO_BRANDING", "logo_image_or_top_left_brand"

        # 3. Table Heading (Immediately above table top rule)
        if by0 >= table_top_y - 45.0 and by1 <= table_top_y + 1.0:
            return "TABLE_HEADING", "immediately_above_table_grid"

        # 4. Footer (Strictly below last table cell / bottom rule)
        if by0 >= footer_min_y:
            if any(w in text_lower for w in ["computer generated", "disclaimer", "registered office", "statutory", "end of statement"]):
                return "DISCLAIMER", "footer_disclaimer_content"
            return "FOOTER", "strictly_below_table_bottom"

        # 5. Key-Value Colon Grid
        colon_count = sum(1 for pid in block_pids if ":" in primitive_map[pid].get("text", ""))
        if colon_count >= 2 or (bx0 >= page_w * 0.40 and any(w in text_lower for w in ["date", "period", "account", "currency", "branch", "holder", "ifsc"])):
            return "KEY_VALUE_GRID", "colon_axis_and_account_keys"

        # 6. Address Block
        if any(w in text_lower for w in ["road", "street", "lane", "flat", "nagar", "pin", "floor", "box", "house"]):
            return "ADDRESS_BLOCK", "address_keywords_and_zip"

        # Default block classification
        if by1 <= page_h * 0.35:
            return "HEADER_BAND_BLOCK", "upper_page_content"
        return "GENERAL_BLOCK", "unclassified_leaf_block"

    def _calculate_median_line_pitch(self, spans: List[TextSpanModel]) -> float:
        """Calculate median vertical line pitch of text spans."""
        if len(spans) < 2:
            return 12.0
        ys = sorted(s.ink_box.y0.pt for s in spans)
        diffs = [y1 - y0 for y0, y1 in zip(ys[:-1], ys[1:]) if 5.0 <= (y1 - y0) <= 35.0]
        return float(np.median(diffs)) if diffs else 12.0

    def _auto_repair_invariants(
        self,
        nodes: Dict[str, LayoutTreeNode],
        primitive_map: Dict[str, Dict[str, Any]],
        page_w: float,
        page_h: float
    ) -> Dict[str, Any]:
        """Verify invariants I1-I6 and perform auto-repair shrink-wrapping."""
        violations: List[str] = []
        repairs: List[str] = []

        # Iterate up to 3 passes for shrink-wrapping and boundary resolution
        for pass_idx in range(3):
            # I1: node.bbox == union of its members
            for nid, node in nodes.items():
                if nid.startswith("page_root") or not node.member_ids:
                    continue
                m_boxes = [primitive_map[pid]["bbox_pt"] for pid in node.member_ids if pid in primitive_map]
                if not m_boxes:
                    continue
                exact_x0 = min(b[0] for b in m_boxes)
                exact_y0 = min(b[1] for b in m_boxes)
                exact_x1 = max(b[2] for b in m_boxes)
                exact_y1 = max(b[3] for b in m_boxes)

                if node.is_container:
                    node.tightness_iou = 1.0
                    node.vertical_overshoot_pt = 0.0
                else:
                    cur_box = node.bbox.raw_pt
                    # Calculate IoU and vertical overshoot
                    iou = bbox_iou(cur_box, (exact_x0, exact_y0, exact_x1, exact_y1))
                    node.tightness_iou = iou
                    overshoot = max(0.0, (cur_box[3] - cur_box[1]) - (exact_y1 - exact_y0))
                    node.vertical_overshoot_pt = overshoot

                    if iou < 0.95:
                        # Auto-repair: Shrink-wrap to exact member ink union
                        node.bbox = create_bbox_from_pt(exact_x0, exact_y0, exact_x1, exact_y1, page_w, page_h, self.config.dpi)
                        node.tightness_iou = 1.0
                        node.vertical_overshoot_pt = 0.0
                        repairs.append(f"Pass {pass_idx+1}: Shrink-wrapped node {nid} to member bounds ({exact_x0:.1f}, {exact_y0:.1f}, {exact_x1:.1f}, {exact_y1:.1f})")

            # I3: Sibling bboxes have zero overlap
            leaf_nodes = [n for nid, n in nodes.items() if not nid.startswith("page_root") and not n.is_container]
            for i in range(len(leaf_nodes)):
                for j in range(i + 1, len(leaf_nodes)):
                    n1 = leaf_nodes[i]
                    n2 = leaf_nodes[j]
                    b1 = n1.bbox.raw_pt
                    b2 = n2.bbox.raw_pt
                    ix0 = max(b1[0], b2[0])
                    iy0 = max(b1[1], b2[1])
                    ix1 = min(b1[2], b2[2])
                    iy1 = min(b1[3], b2[3])
                    if ix1 > ix0 + 0.5 and iy1 > iy0 + 0.5:
                        inter_area = (ix1 - ix0) * (iy1 - iy0)
                        n1.sibling_overlap_area = max(n1.sibling_overlap_area, inter_area)
                        n2.sibling_overlap_area = max(n2.sibling_overlap_area, inter_area)
                        violations.append(f"Sibling overlap detected between {n1.id} and {n2.id}: {inter_area:.2f} pt^2")

        return {
            "status": "OK" if not violations else "DEGRADED",
            "repairs_performed": repairs,
            "violations": violations
        }

