"""
PDF Content-Stream Interpreter & ByteLayer Extractor.
Executes content stream operators against the graphics state machine, resolving Form XObjects
recursively, applying ToUnicode CMaps and FontTools metrics, and outputting PageByteLayer primitives.
"""

from __future__ import annotations
import io
import math
import os
from typing import List, Dict, Tuple, Optional, Any, Union
import pikepdf
from pdf_analyzer.l0_bytes.primitives import (
    ByteRange,
    StreamProvenance,
    Color,
    StrokeStyle,
    FontMetrics,
    PaintedPath,
    PaintedTextChar,
    InlineImageInstance,
    FormXObjectInstance,
    ClippingRegion,
    PageByteLayer,
)
from pdf_analyzer.l0_bytes.tokenizer import tokenize_content_stream, Token
from pdf_analyzer.l0_bytes.state import GraphicsState, CTM, TextState
from pdf_analyzer.l0_bytes.geometry import (
    transform_point,
    transform_bbox,
    build_stroked_polygon,
    build_filled_polygon,
)
from pdf_analyzer.l0_bytes.fonts import create_font_metrics


class ByteLayerExtractor:
    """
    Extracts L0 ByteLayer primitives from a PDF document page.
    """

    def __init__(self, pdf_source: Union[str, bytes, pikepdf.Pdf]):
        self.pdf_path: Optional[str] = pdf_source if isinstance(pdf_source, str) else None
        if isinstance(pdf_source, str):
            self.pdf = pikepdf.Pdf.open(pdf_source)
            self._owns_pdf = True
        elif isinstance(pdf_source, (bytes, bytearray)):
            self.pdf = pikepdf.Pdf.open(io.BytesIO(pdf_source))
            self._owns_pdf = True
        elif isinstance(pdf_source, pikepdf.Pdf):
            self.pdf = pdf_source
            self._owns_pdf = False
        else:
            raise TypeError("pdf_source must be a file path, bytes, or pikepdf.Pdf instance")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_pdf:
            self.pdf.close()

    def extract_page(self, page_number: int = 1) -> PageByteLayer:
        """
        Extracts L0 primitives for the specified 1-indexed page.
        """
        if page_number < 1 or page_number > len(self.pdf.pages):
            raise ValueError(f"Invalid page number {page_number}. PDF has {len(self.pdf.pages)} pages.")

        pike_page = self.pdf.pages[page_number - 1]

        # Extract MediaBox and CropBox without hardcoded fallbacks (Rule 5)
        if hasattr(pike_page, "mediabox") and pike_page.mediabox:
            mediabox = [float(v) for v in pike_page.mediabox]
        elif pikepdf.Name("/MediaBox") in pike_page:
            mediabox = [float(v) for v in pike_page[pikepdf.Name("/MediaBox")]]
        else:
            p = pike_page.get(pikepdf.Name("/Parent"))
            mb_found = None
            while p is not None:
                if pikepdf.Name("/MediaBox") in p:
                    mb_found = [float(v) for v in p[pikepdf.Name("/MediaBox")]]
                    break
                p = p.get(pikepdf.Name("/Parent"))
            if mb_found is not None:
                mediabox = mb_found
            else:
                raise ValueError(f"Page {page_number} has no /MediaBox defined or inherited.")

        if hasattr(pike_page, "cropbox") and pike_page.cropbox:
            cropbox = [float(v) for v in pike_page.cropbox]
        elif pikepdf.Name("/CropBox") in pike_page:
            cropbox = [float(v) for v in pike_page[pikepdf.Name("/CropBox")]]
        else:
            cropbox = list(mediabox)
        rotate = int(pike_page.get(pikepdf.Name("/Rotate"), 0))

        page_layer = PageByteLayer(
            page_number=page_number,
            mediabox_pt=(mediabox[0], mediabox[1], mediabox[2], mediabox[3]),
            cropbox_pt=(cropbox[0], cropbox[1], cropbox[2], cropbox[3]),
            rotation_deg=rotate,
            pdf_path=self.pdf_path,
        )

        # Build font metrics dictionary from Page Resources
        fonts_cache: Dict[str, FontMetrics] = {}
        resources = pike_page.get(pikepdf.Name("/Resources"), None)
        if resources is not None:
            self._load_font_resources(resources, fonts_cache)

        # Get Page Contents Stream bytes
        contents_data = self._get_stream_data(pike_page.get(pikepdf.Name("/Contents"), None))

        # Initial Graphics State
        initial_state = GraphicsState()
        # Set default PDF coordinate system CTM
        initial_state.ctm = CTM.identity()

        # Execute Page Stream
        self._execute_stream(
            stream_data=contents_data,
            stream_name=f"Page_{page_number}_Contents",
            state=initial_state,
            resources=resources,
            fonts_cache=fonts_cache,
            page_layer=page_layer,
            xobject_stack=(),
        )

        page_layer.fonts = dict(fonts_cache)

        # Detect Type3 glyphs and outline paths (non-text glyphs)
        for ch in page_layer.chars:
            fm = fonts_cache.get(ch.font_name)
            if fm and fm.is_type3:
                page_layer.non_text_glyphs.append({
                    "type": "type3_glyph",
                    "char": ch.char_text,
                    "bbox_pt": list(ch.font_bbox_device_pt),
                    "font_name": ch.font_name,
                })

        text_bboxes = [c.font_bbox_device_pt for c in page_layer.chars if c.font_bbox_device_pt]
        for path in page_layer.paths:
            bbox = path.painted_bbox_device_pt or path.bbox_device_pt
            if bbox and len(bbox) == 4:
                w = abs(bbox[2] - bbox[0])
                h = abs(bbox[3] - bbox[1])
                if 2.0 <= w <= 24.0 and 2.0 <= h <= 24.0:
                    has_close = any(s[0] in ("h", "re") for s in path.segments) or len(path.segments) >= 4
                    overlaps_text = any(
                        max(0.0, min(bbox[2], tb[2]) - max(bbox[0], tb[0])) > 0.5 and
                        max(0.0, min(bbox[3], tb[3]) - max(bbox[1], tb[1])) > 0.5
                        for tb in text_bboxes
                    )
                    if has_close and not overlaps_text and (path.fill_color or path.fill_rule):
                        page_layer.non_text_glyphs.append({
                            "type": "path_outline_glyph",
                            "path_id": path.path_id,
                            "bbox_pt": [round(float(v), 3) for v in bbox],
                        })

        return page_layer

    def _get_stream_data(self, contents_obj: Any) -> bytes:
        if contents_obj is None:
            return b""
        if isinstance(contents_obj, pikepdf.Array):
            chunks = []
            for item in contents_obj:
                try:
                    chunks.append(bytes(item.read_bytes()))
                except Exception:
                    pass
            return b"\n".join(chunks)
        elif isinstance(contents_obj, pikepdf.Stream):
            try:
                return bytes(contents_obj.read_bytes())
            except Exception:
                return b""
        return b""

    def _load_font_resources(self, resources_obj: Any, fonts_cache: Dict[str, FontMetrics]) -> None:
        if resources_obj is None or pikepdf.Name("/Font") not in resources_obj:
            return
        font_dict = resources_obj[pikepdf.Name("/Font")]
        for font_key, font_val in font_dict.items():
            font_name = str(font_key).lstrip("/")
            base_font = str(font_val.get(pikepdf.Name("/BaseFont"), font_name)).lstrip("/")

            to_unicode_bytes = None
            if pikepdf.Name("/ToUnicode") in font_val:
                try:
                    to_unicode_bytes = bytes(font_val[pikepdf.Name("/ToUnicode")].read_bytes())
                except Exception:
                    pass

            font_file_bytes = None
            fd = None
            if pikepdf.Name("/FontDescriptor") in font_val:
                fd = font_val[pikepdf.Name("/FontDescriptor")]
            elif pikepdf.Name("/DescendantFonts") in font_val:
                try:
                    df_first = font_val[pikepdf.Name("/DescendantFonts")][0]
                    if pikepdf.Name("/FontDescriptor") in df_first:
                        fd = df_first[pikepdf.Name("/FontDescriptor")]
                except Exception:
                    pass

            if fd is not None:
                for ff_key in ["/FontFile", "/FontFile2", "/FontFile3"]:
                    if pikepdf.Name(ff_key) in fd:
                        try:
                            font_file_bytes = bytes(fd[pikepdf.Name(ff_key)].read_bytes())
                            break
                        except Exception:
                            pass

            font_dict_info = {}
            font_subtype = str(font_val.get(pikepdf.Name("/Subtype"), "")).lstrip("/")
            is_type0 = font_subtype == "Type0"
            font_dict_info["is_type0"] = is_type0

            if fd is not None:
                if pikepdf.Name("/Ascent") in fd:
                    try:
                        font_dict_info["ascent"] = float(fd[pikepdf.Name("/Ascent")])
                    except Exception:
                        pass
                if pikepdf.Name("/Descent") in fd:
                    try:
                        font_dict_info["descent"] = float(fd[pikepdf.Name("/Descent")])
                    except Exception:
                        pass
                if pikepdf.Name("/CapHeight") in fd:
                    try:
                        font_dict_info["cap_height"] = float(fd[pikepdf.Name("/CapHeight")])
                    except Exception:
                        pass
                if pikepdf.Name("/FontBBox") in fd:
                    try:
                        font_dict_info["font_bbox"] = [float(v) for v in fd[pikepdf.Name("/FontBBox")]]
                    except Exception:
                        pass

            if pikepdf.Name("/DescendantFonts") in font_val:
                try:
                    df = font_val[pikepdf.Name("/DescendantFonts")][0]
                    if pikepdf.Name("/W") in df:
                        from pdf_analyzer.l0_bytes.fonts import parse_cid_widths
                        font_dict_info["cid_widths"] = parse_cid_widths(df[pikepdf.Name("/W")])
                    if pikepdf.Name("/DW") in df:
                        font_dict_info["default_width"] = float(df[pikepdf.Name("/DW")])
                except Exception:
                    pass

            if pikepdf.Name("/FirstChar") in font_val and pikepdf.Name("/Widths") in font_val:
                try:
                    first_char = int(font_val[pikepdf.Name("/FirstChar")])
                    widths_arr = [float(w) for w in font_val[pikepdf.Name("/Widths")]]
                    font_dict_info["first_char"] = first_char
                    font_dict_info["widths"] = widths_arr
                except Exception:
                    pass

            fm = create_font_metrics(
                font_name=font_name,
                base_font=base_font,
                font_dict=font_dict_info if font_dict_info else None,
                font_file_bytes=font_file_bytes,
                to_unicode_bytes=to_unicode_bytes,
            )
            fonts_cache[font_name] = fm
            fonts_cache[base_font] = fm

    def _execute_stream(
        self,
        stream_data: bytes,
        stream_name: str,
        state: GraphicsState,
        resources: Any,
        fonts_cache: Dict[str, FontMetrics],
        page_layer: PageByteLayer,
        xobject_stack: Tuple[str, ...],
    ) -> None:
        if not stream_data:
            return

        tokens = list(tokenize_content_stream(stream_data))
        num_tokens = len(tokens)
        token_idx = 0

        state_stack: List[GraphicsState] = []
        current_path_segments: List[Tuple[Any, ...]] = []
        current_clip_rule: Optional[str] = None
        oper_seq_id = 0
        marked_content_tag: Optional[str] = None
        mcid: Optional[int] = None

        operand_stack: List[Any] = []

        while token_idx < num_tokens:
            t = tokens[token_idx]
            token_idx += 1

            if t.type in ("NUMBER", "NAME", "STRING", "HEX_STRING"):
                operand_stack.append(t.value)
                continue
            elif t.type == "ARRAY_START":
                # Collect array items
                arr = []
                while token_idx < num_tokens and tokens[token_idx].type != "ARRAY_END":
                    sub_t = tokens[token_idx]
                    if sub_t.type in ("NUMBER", "NAME", "STRING", "HEX_STRING"):
                        arr.append(sub_t.value)
                    token_idx += 1
                if token_idx < num_tokens and tokens[token_idx].type == "ARRAY_END":
                    token_idx += 1
                operand_stack.append(arr)
                continue
            elif t.type == "DICT_START":
                # Skip inline dict tokens in operands
                while token_idx < num_tokens and tokens[token_idx].type != "DICT_END":
                    token_idx += 1
                if token_idx < num_tokens and tokens[token_idx].type == "DICT_END":
                    token_idx += 1
                continue
            elif t.type != "OPERATOR":
                continue

            # Operator encountered
            op = t.value
            oper_seq_id += 1
            prov = StreamProvenance(
                stream_name=stream_name,
                byte_range=t.byte_range,
                operator_index=oper_seq_id,
                operator_name=op,
                xobject_stack=xobject_stack,
                marked_content_tag=marked_content_tag,
                mcid=mcid,
            )

            # ----------------------------------------------------
            # 1. Graphics State Operators: q, Q, cm, w, J, j, M, d, ri, i, gs
            # ----------------------------------------------------
            if op == "q":
                state_stack.append(state.clone())
            elif op == "Q":
                if state_stack:
                    state = state_stack.pop()
            elif op == "cm" and len(operand_stack) >= 6:
                a, b, c, d, e, f = [float(v) for v in operand_stack[-6:]]
                new_m = CTM(a, b, c, d, e, f)
                state.ctm = new_m.multiply(state.ctm)
                operand_stack.clear()
            elif op == "w" and operand_stack:
                state.stroke_style = StrokeStyle(
                    width_pt=float(operand_stack[-1]),
                    cap=state.stroke_style.cap,
                    join=state.stroke_style.join,
                    miter_limit=state.stroke_style.miter_limit,
                    dash_pattern=state.stroke_style.dash_pattern,
                    dash_phase=state.stroke_style.dash_phase,
                )
            elif op == "J" and operand_stack:
                state.stroke_style = StrokeStyle(
                    width_pt=state.stroke_style.width_pt,
                    cap=int(operand_stack[-1]),
                    join=state.stroke_style.join,
                    miter_limit=state.stroke_style.miter_limit,
                    dash_pattern=state.stroke_style.dash_pattern,
                    dash_phase=state.stroke_style.dash_phase,
                )
            elif op == "j" and operand_stack:
                state.stroke_style = StrokeStyle(
                    width_pt=state.stroke_style.width_pt,
                    cap=state.stroke_style.cap,
                    join=int(operand_stack[-1]),
                    miter_limit=state.stroke_style.miter_limit,
                    dash_pattern=state.stroke_style.dash_pattern,
                    dash_phase=state.stroke_style.dash_phase,
                )
            elif op == "M" and operand_stack:
                state.stroke_style = StrokeStyle(
                    width_pt=state.stroke_style.width_pt,
                    cap=state.stroke_style.cap,
                    join=state.stroke_style.join,
                    miter_limit=float(operand_stack[-1]),
                    dash_pattern=state.stroke_style.dash_pattern,
                    dash_phase=state.stroke_style.dash_phase,
                )
            elif op == "d" and len(operand_stack) >= 2:
                pattern = operand_stack[-2] if isinstance(operand_stack[-2], list) else ()
                phase = float(operand_stack[-1])
                state.stroke_style = StrokeStyle(
                    width_pt=state.stroke_style.width_pt,
                    cap=state.stroke_style.cap,
                    join=state.stroke_style.join,
                    miter_limit=state.stroke_style.miter_limit,
                    dash_pattern=tuple(float(x) for x in pattern),
                    dash_phase=phase,
                )

            # ----------------------------------------------------
            # 2. Color Operators: g, G, rg, RG, k, K, cs, CS, sc, SC, scn, SCN, gs
            # ----------------------------------------------------
            elif op == "g" and operand_stack:
                val = float(operand_stack[-1])
                curr_a = state.fill_color.alpha if state.fill_color else 1.0
                state.fill_color = Color("DeviceGray", (val,), alpha=curr_a)
            elif op == "G" and operand_stack:
                val = float(operand_stack[-1])
                curr_a = state.stroke_color.alpha if state.stroke_color else 1.0
                state.stroke_color = Color("DeviceGray", (val,), alpha=curr_a)
            elif op == "rg" and len(operand_stack) >= 3:
                r, g, b = [float(v) for v in operand_stack[-3:]]
                curr_a = state.fill_color.alpha if state.fill_color else 1.0
                state.fill_color = Color("DeviceRGB", (r, g, b), alpha=curr_a)
            elif op == "RG" and len(operand_stack) >= 3:
                r, g, b = [float(v) for v in operand_stack[-3:]]
                curr_a = state.stroke_color.alpha if state.stroke_color else 1.0
                state.stroke_color = Color("DeviceRGB", (r, g, b), alpha=curr_a)
            elif op == "k" and len(operand_stack) >= 4:
                c, m, y, k_val = [float(v) for v in operand_stack[-4:]]
                curr_a = state.fill_color.alpha if state.fill_color else 1.0
                state.fill_color = Color("DeviceCMYK", (c, m, y, k_val), alpha=curr_a)
            elif op == "K" and len(operand_stack) >= 4:
                c, m, y, k_val = [float(v) for v in operand_stack[-4:]]
                curr_a = state.stroke_color.alpha if state.stroke_color else 1.0
                state.stroke_color = Color("DeviceCMYK", (c, m, y, k_val), alpha=curr_a)
            elif op in ("sc", "scn") and operand_stack:
                vals = tuple(float(v) for v in operand_stack)
                curr_a = state.fill_color.alpha if state.fill_color else 1.0
                if len(vals) == 1:
                    state.fill_color = Color("DeviceGray", vals, alpha=curr_a)
                elif len(vals) == 3:
                    state.fill_color = Color("DeviceRGB", vals, alpha=curr_a)
                elif len(vals) >= 4:
                    state.fill_color = Color("DeviceCMYK", vals[:4], alpha=curr_a)
            elif op in ("SC", "SCN") and operand_stack:
                vals = tuple(float(v) for v in operand_stack)
                curr_a = state.stroke_color.alpha if state.stroke_color else 1.0
                if len(vals) == 1:
                    state.stroke_color = Color("DeviceGray", vals, alpha=curr_a)
                elif len(vals) == 3:
                    state.stroke_color = Color("DeviceRGB", vals, alpha=curr_a)
                elif len(vals) >= 4:
                    state.stroke_color = Color("DeviceCMYK", vals[:4], alpha=curr_a)
            elif op == "gs" and operand_stack:
                gs_name = str(operand_stack[-1]).lstrip("/")
                if resources is not None and pikepdf.Name("/ExtGState") in resources:
                    ext_gstates = resources[pikepdf.Name("/ExtGState")]
                    pike_gs_key = pikepdf.Name("/" + gs_name)
                    if pike_gs_key in ext_gstates:
                        gs_dict = ext_gstates[pike_gs_key]
                        if pikepdf.Name("/CA") in gs_dict:
                            stroke_a = float(gs_dict[pikepdf.Name("/CA")])
                            if state.stroke_color:
                                state.stroke_color = Color(state.stroke_color.space, state.stroke_color.components, alpha=stroke_a)
                            else:
                                state.stroke_color = Color("DeviceRGB", (0.0, 0.0, 0.0), alpha=stroke_a)
                        if pikepdf.Name("/ca") in gs_dict:
                            fill_a = float(gs_dict[pikepdf.Name("/ca")])
                            if state.fill_color:
                                state.fill_color = Color(state.fill_color.space, state.fill_color.components, alpha=fill_a)
                            else:
                                state.fill_color = Color("DeviceRGB", (0.0, 0.0, 0.0), alpha=fill_a)

            # ----------------------------------------------------
            # 3. Path Construction Operators: m, l, c, v, y, h, re
            # ----------------------------------------------------
            elif op == "m" and len(operand_stack) >= 2:
                current_path_segments.append(("m", float(operand_stack[-2]), float(operand_stack[-1])))
            elif op == "l" and len(operand_stack) >= 2:
                current_path_segments.append(("l", float(operand_stack[-2]), float(operand_stack[-1])))
            elif op == "c" and len(operand_stack) >= 6:
                current_path_segments.append(
                    ("c", float(operand_stack[-6]), float(operand_stack[-5]),
                     float(operand_stack[-4]), float(operand_stack[-3]),
                     float(operand_stack[-2]), float(operand_stack[-1]))
                )
            elif op == "v" and len(operand_stack) >= 4:
                current_path_segments.append(
                    ("v", float(operand_stack[-4]), float(operand_stack[-3]),
                     float(operand_stack[-2]), float(operand_stack[-1]))
                )
            elif op == "y" and len(operand_stack) >= 4:
                current_path_segments.append(
                    ("y", float(operand_stack[-4]), float(operand_stack[-3]),
                     float(operand_stack[-2]), float(operand_stack[-1]))
                )
            elif op == "re" and len(operand_stack) >= 4:
                current_path_segments.append(
                    ("re", float(operand_stack[-4]), float(operand_stack[-3]),
                     float(operand_stack[-2]), float(operand_stack[-1]))
                )
            elif op == "h":
                current_path_segments.append(("h",))

            # ----------------------------------------------------
            # 4. Clipping Path Operators: W, W*
            # ----------------------------------------------------
            elif op in ("W", "W*"):
                current_clip_rule = "nonzero" if op == "W" else "even-odd"

            # ----------------------------------------------------
            # 5. Path Painting Operators: S, s, f, F, f*, B, B*, b, b*, n
            # ----------------------------------------------------
            elif op in ("S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"):
                if op in ("s", "b", "b*"):
                    current_path_segments.append(("h",))

                is_stroke = op in ("S", "s", "B", "B*", "b", "b*")
                is_fill = op in ("f", "F", "f*", "B", "B*", "b", "b*")
                fill_rule = "even-odd" if op in ("f*", "B*", "b*") else "nonzero"

                if current_path_segments:
                    path_id = f"path_p{page_layer.page_number}_{len(page_layer.paths) + 1}"

                    # Vectorize stroked / filled geometry
                    shapely_geom = None
                    raw_bbox = (0.0, 0.0, 0.0, 0.0)
                    painted_bbox = (0.0, 0.0, 0.0, 0.0)

                    if is_stroke:
                        poly, raw_b, paint_b = build_stroked_polygon(
                            segments=current_path_segments,
                            ctm=state.ctm,
                            stroke=state.stroke_style,
                            clipping_shapes=state.clip_polygons,
                        )
                        shapely_geom = poly
                        raw_bbox = raw_b
                        painted_bbox = paint_b
                    elif is_fill:
                        poly, raw_b, paint_b = build_filled_polygon(
                            segments=current_path_segments,
                            ctm=state.ctm,
                            fill_rule=fill_rule,
                            clipping_shapes=state.clip_polygons,
                        )
                        shapely_geom = poly
                        raw_bbox = raw_b
                        painted_bbox = paint_b

                    if is_stroke or is_fill:
                        painted_obj = PaintedPath(
                            path_id=path_id,
                            segments=list(current_path_segments),
                            stroke=state.stroke_style if is_stroke else None,
                            stroke_color=state.stroke_color if is_stroke else None,
                            fill_rule=fill_rule if is_fill else None,
                            fill_color=state.fill_color if is_fill else None,
                            ctm=state.ctm.to_tuple(),
                            bbox_device_pt=raw_bbox,
                            painted_bbox_device_pt=painted_bbox,
                            shapely_geom=shapely_geom,
                            clipping_id=state.clip_id,
                            provenance=prov,
                            ocg_name=state.ocg_name,
                            ocg_visible=state.ocg_visible,
                        )
                        page_layer.paths.append(painted_obj)

                # Process pending clip if W/W* was called
                if current_clip_rule is not None and current_path_segments:
                    clip_poly, _, _ = build_filled_polygon(
                        segments=current_path_segments,
                        ctm=state.ctm,
                        fill_rule=current_clip_rule,
                        clipping_shapes=None,
                    )
                    clip_id = f"clip_{len(page_layer.clips) + 1}"
                    reg = ClippingRegion(
                        clip_id=clip_id,
                        path_segments=list(current_path_segments),
                        winding_rule=current_clip_rule,
                        shapely_geom=clip_poly,
                        parent_clip_id=state.clip_id,
                    )
                    page_layer.clips[clip_id] = reg
                    state.clip_polygons.append(clip_poly)
                    state.clip_id = clip_id
                    current_clip_rule = None

                current_path_segments = []

            # ----------------------------------------------------
            # 6. Text Object Operators: BT, ET, Tf, Tc, Tw, Tz, TL, Tr, Ts
            # ----------------------------------------------------
            elif op == "BT":
                state.text_state.text_matrix = CTM.identity()
                state.text_state.line_matrix = CTM.identity()
            elif op == "ET":
                state.text_state.text_matrix = CTM.identity()
                state.text_state.line_matrix = CTM.identity()
            elif op == "Tf" and len(operand_stack) >= 2:
                state.text_state.font_name = str(operand_stack[-2]).lstrip("/")
                state.text_state.font_size = float(operand_stack[-1])
            elif op == "Tc" and operand_stack:
                state.text_state.char_spacing = float(operand_stack[-1])
            elif op == "Tw" and operand_stack:
                state.text_state.word_spacing = float(operand_stack[-1])
            elif op == "Tz" and operand_stack:
                state.text_state.horizontal_scaling = float(operand_stack[-1])
            elif op == "TL" and operand_stack:
                state.text_state.leading = float(operand_stack[-1])
            elif op == "Tr" and operand_stack:
                state.text_state.rendering_mode = int(operand_stack[-1])
            elif op == "Ts" and operand_stack:
                state.text_state.rise = float(operand_stack[-1])

            # ----------------------------------------------------
            # 7. Text Positioning Operators: Td, TD, Tm, T*
            # ----------------------------------------------------
            elif op == "Td" and len(operand_stack) >= 2:
                tx, ty = float(operand_stack[-2]), float(operand_stack[-1])
                t_shift = CTM(1, 0, 0, 1, tx, ty)
                state.text_state.line_matrix = t_shift.multiply(state.text_state.line_matrix)
                state.text_state.text_matrix = CTM(*state.text_state.line_matrix.to_tuple())
            elif op == "TD" and len(operand_stack) >= 2:
                tx, ty = float(operand_stack[-2]), float(operand_stack[-1])
                state.text_state.leading = -ty
                t_shift = CTM(1, 0, 0, 1, tx, ty)
                state.text_state.line_matrix = t_shift.multiply(state.text_state.line_matrix)
                state.text_state.text_matrix = CTM(*state.text_state.line_matrix.to_tuple())
            elif op == "Tm" and len(operand_stack) >= 6:
                a, b, c, d, e, f = [float(v) for v in operand_stack[-6:]]
                state.text_state.text_matrix = CTM(a, b, c, d, e, f)
                state.text_state.line_matrix = CTM(a, b, c, d, e, f)
            elif op == "T*":
                t_shift = CTM(1, 0, 0, 1, 0.0, -state.text_state.leading)
                state.text_state.line_matrix = t_shift.multiply(state.text_state.line_matrix)
                state.text_state.text_matrix = CTM(*state.text_state.line_matrix.to_tuple())

            # ----------------------------------------------------
            # 8. Text Showing Operators: Tj, ', ", TJ
            # ----------------------------------------------------
            elif op in ("Tj", "'", '"') and operand_stack:
                if op == "'":
                    t_shift = CTM(1, 0, 0, 1, 0.0, -state.text_state.leading)
                    state.text_state.line_matrix = t_shift.multiply(state.text_state.line_matrix)
                    state.text_state.text_matrix = CTM(*state.text_state.line_matrix.to_tuple())
                elif op == '"' and len(operand_stack) >= 3:
                    state.text_state.word_spacing = float(operand_stack[-3])
                    state.text_state.char_spacing = float(operand_stack[-2])
                    t_shift = CTM(1, 0, 0, 1, 0.0, -state.text_state.leading)
                    state.text_state.line_matrix = t_shift.multiply(state.text_state.line_matrix)
                    state.text_state.text_matrix = CTM(*state.text_state.line_matrix.to_tuple())

                raw_text_val = operand_stack[-1]
                self._render_text_string(raw_text_val, state, fonts_cache, page_layer, prov)
            elif op == "TJ" and operand_stack:
                tj_array = operand_stack[-1]
                if isinstance(tj_array, list):
                    self._render_text_array(tj_array, state, fonts_cache, page_layer, prov)

            # ----------------------------------------------------
            # 9. XObject Painting: Do
            # ----------------------------------------------------
            elif op == "Do" and operand_stack:
                xobj_name = str(operand_stack[-1]).lstrip("/")
                self._handle_do_xobject(
                    xobj_name=xobj_name,
                    state=state,
                    resources=resources,
                    fonts_cache=fonts_cache,
                    page_layer=page_layer,
                    prov=prov,
                    xobject_stack=xobject_stack,
                )

            # ----------------------------------------------------
            # 10. Marked Content & OCG: BDC, BMC, EMC
            # ----------------------------------------------------
            elif op == "BMC" and operand_stack:
                marked_content_tag = str(operand_stack[-1]).lstrip("/")
            elif op == "BDC" and len(operand_stack) >= 2:
                marked_content_tag = str(operand_stack[-2]).lstrip("/")
                props = operand_stack[-1]
                if isinstance(props, dict) and "MCID" in props:
                    mcid = int(props["MCID"])
            elif op == "EMC":
                marked_content_tag = None
                mcid = None

            operand_stack.clear()

    def _render_text_string(
        self,
        raw_val: Union[str, bytes],
        state: GraphicsState,
        fonts_cache: Dict[str, FontMetrics],
        page_layer: PageByteLayer,
        prov: StreamProvenance,
    ) -> None:
        if isinstance(raw_val, str):
            raw_bytes = raw_val.encode("latin1", errors="replace")
        elif isinstance(raw_val, bytes):
            raw_bytes = raw_val
        else:
            return

        ts = state.text_state
        fm = fonts_cache.get(ts.font_name, fonts_cache.get(ts.font_name.split("+")[-1], FontMetrics(ts.font_name, ts.font_name)))
        fs = ts.font_size
        th = ts.horizontal_scaling / 100.0
        tc = ts.char_spacing
        tw = ts.word_spacing

        # Collect character / CID codes
        codes: List[int] = []
        if fm.is_type0:
            i = 0
            while i < len(raw_bytes):
                if i + 1 < len(raw_bytes):
                    cid = (raw_bytes[i] << 8) | raw_bytes[i + 1]
                    codes.append(cid)
                    i += 2
                else:
                    codes.append(raw_bytes[i])
                    i += 1
        else:
            codes = [int(b) for b in raw_bytes]

        for char_code in codes:
            # Map code to unicode character
            char_str = chr(char_code) if char_code < 256 else "?"
            unicode_char = fm.to_unicode_map.get(char_code, char_str)

            # Advance width from font metrics
            glyph_w = fm.widths.get(char_code, fm.default_width)
            w0 = (glyph_w / fm.units_per_em) * fs

            # Character device origin
            effective_tm = ts.text_matrix.multiply(state.ctm)
            origin_x, origin_y = effective_tm.transform_point(0.0, ts.rise)

            # Font bbox in device coordinates
            ascent_dev = (fm.ascent / fm.units_per_em) * fs
            descent_dev = (fm.descent / fm.units_per_em) * fs
            advance_dev = w0 * th

            # Corner points
            p0 = effective_tm.transform_point(0.0, descent_dev + ts.rise)
            p1 = effective_tm.transform_point(w0 * th, descent_dev + ts.rise)
            p2 = effective_tm.transform_point(w0 * th, ascent_dev + ts.rise)
            p3 = effective_tm.transform_point(0.0, ascent_dev + ts.rise)

            xs = [p0[0], p1[0], p2[0], p3[0]]
            ys = [p0[1], p1[1], p2[1], p3[1]]
            font_bbox = (min(xs), min(ys), max(xs), max(ys))

            # Spacing delta
            delta_spacing = tc + (tw if char_code == 32 else 0.0)
            advance_total = (w0 + delta_spacing) * th

            char_id = f"char_p{page_layer.page_number}_{len(page_layer.chars) + 1}"
            char_obj = PaintedTextChar(
                char_id=char_id,
                char_code=char_code,
                char_text=char_str,
                unicode_text=unicode_char,
                font_name=ts.font_name,
                font_size_pt=fs,
                text_matrix=ts.text_matrix.to_tuple(),
                ctm=state.ctm.to_tuple(),
                origin_device_pt=(origin_x, origin_y),
                advance_pt=advance_total,
                font_bbox_device_pt=font_bbox,
                ink_bbox_device_pt=font_bbox,
                fill_color=state.fill_color,
                stroke_color=state.stroke_color,
                rendering_mode=ts.rendering_mode,
                char_spacing_pt=tc,
                word_spacing_pt=tw,
                horiz_scaling=ts.horizontal_scaling,
                rise_pt=ts.rise,
                clipping_id=state.clip_id,
                provenance=prov,
                ocg_name=state.ocg_name,
                ocg_visible=state.ocg_visible,
            )
            page_layer.chars.append(char_obj)

            # Advance text matrix horizontally: Tm = [1 0 0 1 tx 0] * Tm
            shift_tm = CTM(1.0, 0.0, 0.0, 1.0, advance_total, 0.0)
            ts.text_matrix = shift_tm.multiply(ts.text_matrix)

    def _render_text_array(
        self,
        tj_array: List[Any],
        state: GraphicsState,
        fonts_cache: Dict[str, FontMetrics],
        page_layer: PageByteLayer,
        prov: StreamProvenance,
    ) -> None:
        ts = state.text_state
        fm = fonts_cache.get(ts.font_name, fonts_cache.get(ts.font_name.split("+")[-1], FontMetrics(ts.font_name, ts.font_name)))
        fs = ts.font_size
        th = ts.horizontal_scaling / 100.0

        for item in tj_array:
            if isinstance(item, (int, float)):
                # Kerning displacement: tx = - (num / 1000.0) * fs * (th / 100.0)
                displacement = -(float(item) / 1000.0) * fs * th
                shift_tm = CTM(1.0, 0.0, 0.0, 1.0, displacement, 0.0)
                ts.text_matrix = shift_tm.multiply(ts.text_matrix)
            elif isinstance(item, (str, bytes)):
                self._render_text_string(item, state, fonts_cache, page_layer, prov)

    def _handle_do_xobject(
        self,
        xobj_name: str,
        state: GraphicsState,
        resources: Any,
        fonts_cache: Dict[str, FontMetrics],
        page_layer: PageByteLayer,
        prov: StreamProvenance,
        xobject_stack: Tuple[str, ...],
    ) -> None:
        if resources is None or pikepdf.Name("/XObject") not in resources:
            return
        xobjects_dict = resources[pikepdf.Name("/XObject")]
        pike_xobj_key = pikepdf.Name("/" + xobj_name)
        if pike_xobj_key not in xobjects_dict:
            return

        xobj = xobjects_dict[pike_xobj_key]
        subtype = str(xobj.get(pikepdf.Name("/Subtype"), "")).lstrip("/")

        if subtype == "Form":
            # Form XObject
            matrix = [float(v) for v in xobj.get(pikepdf.Name("/Matrix"), [1, 0, 0, 1, 0, 0])]
            bbox = [float(v) for v in xobj.get(pikepdf.Name("/BBox"), [0, 0, 100, 100])]

            form_ctm = CTM(matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5])
            form_state = state.clone()
            form_state.ctm = form_ctm.multiply(state.ctm)

            form_res = xobj.get(pikepdf.Name("/Resources"), resources)
            if form_res is not None:
                self._load_font_resources(form_res, fonts_cache)

            form_stream = self._get_stream_data(xobj)
            paths_before = len(page_layer.paths)
            chars_before = len(page_layer.chars)

            self._execute_stream(
                stream_data=form_stream,
                stream_name=f"FormXObject_{xobj_name}",
                state=form_state,
                resources=form_res,
                fonts_cache=fonts_cache,
                page_layer=page_layer,
                xobject_stack=xobject_stack + (xobj_name,),
            )

            inst = FormXObjectInstance(
                xobject_id=xobj_name,
                matrix=(matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5]),
                bbox_pt=(bbox[0], bbox[1], bbox[2], bbox[3]),
                paths_count=len(page_layer.paths) - paths_before,
                chars_count=len(page_layer.chars) - chars_before,
                provenance=prov,
            )
            page_layer.xobjects.append(inst)

        elif subtype == "Image":
            # Raster Image XObject
            w = int(xobj.get(pikepdf.Name("/Width"), 1))
            h = int(xobj.get(pikepdf.Name("/Height"), 1))
            bpc = int(xobj.get(pikepdf.Name("/BitsPerComponent"), 8))
            cs = str(xobj.get(pikepdf.Name("/ColorSpace"), "DeviceRGB")).lstrip("/")

            img_bbox = transform_bbox(state.ctm, (0.0, 0.0, 1.0, 1.0))
            img_id = f"img_{xobj_name}_{len(page_layer.images) + 1}"
            img_inst = InlineImageInstance(
                image_id=img_id,
                width_px=w,
                height_px=h,
                bits_per_component=bpc,
                color_space=cs,
                ctm=state.ctm.to_tuple(),
                bbox_device_pt=img_bbox,
                provenance=prov,
            )
            page_layer.images.append(img_inst)
