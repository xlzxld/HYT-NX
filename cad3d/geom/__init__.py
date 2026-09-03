# -*- coding: utf-8 -*-
"""cad3d.geom —— 几何模型、DXF 解析、拓扑与评估工具包。"""

from cad3d.geom.entities import DXLine, DXArc, DXCircle
from cad3d.geom.dxf_parser import _read_dxf_text, entities_of, parse_dxf
from cad3d.geom.topo import (
    _pkey, _near_keys, find_chains, loop_polygon, poly_area, _bbox,
    point_in_poly, _loop_in_loop, organize_loops, _chain_tips, _cluster_tips,
    _merge_open_chains, _center_seen, collect_circle_anchors,
    _chain_outlet_mids, _chain_connectors
)
from cad3d.geom.eval import (
    _q, _nx_curve_fp, _dxf_ent_fp, dxf_fingerprints, _faces_healthy,
    _flush_start_r, _dome_body_ok, _blend_ok, _conn_face_pick, _jrt_sides
)
