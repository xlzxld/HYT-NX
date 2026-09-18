# -*- coding: utf-8 -*-
"""cad3d.geom —— 几何模型、DXF 解析、拓扑与评估工具包。"""

from cad3d.geom.dwg_converter import (
    DwgConversionError,
    convert_dwg_to_dxf,
    find_acad_executable,
)
from cad3d.geom.dxf_parser import _read_dxf_text, entities_of, parse_dxf
from cad3d.geom.entities import DXArc, DXCircle, DXLine
from cad3d.geom.eval import (
    _blend_ok,
    _conn_face_pick,
    _dome_body_ok,
    _dxf_ent_fp,
    _faces_healthy,
    _flush_start_r,
    _jrt_sides,
    _nx_curve_fp,
    _q,
    dxf_fingerprints,
)
from cad3d.geom.topo import (
    _bbox,
    _center_seen,
    _chain_connectors,
    _chain_outlet_mids,
    _chain_tips,
    _cluster_tips,
    _loop_in_loop,
    _merge_open_chains,
    _near_keys,
    _pkey,
    collect_circle_anchors,
    collect_yxb_anchors,  # noqa: F401 —— 纯再导出(本文件同款豁免)
    find_chains,
    loop_polygon,
    organize_loops,
    point_in_poly,
    poly_area,
)
