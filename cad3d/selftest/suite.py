# -*- coding: utf-8 -*-
"""cad3d.selftest.suite —— 离线全量自测套件(150+ 项断言)。"""

import ast
import builtins
import inspect as _insp
import io
import json
import math
import os
import shutil as _sh
import sys
import tempfile as _tf
import time
import xml.etree.ElementTree as ET

from cad3d.core.paths import (
    script_dir, _fresh_dlx_path, _json_path, _temp_dlx_path, resolve_dxf_path,
    _logs_dir
)
from cad3d.core.config import (
    _CFG_NOTES, _cfg, _cfg_num, _cfg_int, _USER_CFG, SCHEMA_VERSION
)
from cad3d.core.constants import (
    _LINK_OFFSETS, JRT_FROM_TOP, DEFAULT_JRT, MANAGED_MAX, STDPARTS_DIRNAME,
    JT_LINK_DEFAULT, JRT_FIELDS, LAYER_SEL_OPTS, BOOL_OPTS, ZMODE_OPTS,
    _ZMODE_FALLBACK, _ZMODE_DEFS, STD_MAX_ANCHORS, LAYER_CODES, DIR_OPTS,
    LINE_ANCHOR_LAYERS, assign_layers
)
from cad3d.core.state import (
    _jt_link_values, jt_mode_with_memory, _cx_link_values, derive_linked,
    jrt_with_memory, default_params, load_state, _name_list, save_state,
    merge_params, merge_jrt
)
from cad3d.core.logging import Log, _fmt_num
from cad3d.geom.entities import DXLine, DXArc, DXCircle
from cad3d.geom.dxf_parser import parse_dxf
from cad3d.geom.topo import (
    find_chains, loop_polygon, poly_area, _bbox, point_in_poly,
    _loop_in_loop, organize_loops, _chain_tips, _cluster_tips,
    _merge_open_chains, _center_seen, collect_circle_anchors,
    collect_yxb_anchors, _chain_outlet_mids, _chain_connectors,
    _contour_outlet_mids, _fbx_anchor_points, _marker_mids_for_chains,
    _merge_marker_lines, _chain_head_tail, _reorder_group_chains,
    _stub_line_indices
)
from cad3d.geom.eval import (
    _dxf_ent_fp, dxf_fingerprints, _faces_healthy, _flush_start_r,
    _dome_body_ok, _blend_ok, _blend_effective, _conn_face_pick, _jrt_sides,
    _flush_blend_allowed
)
from cad3d.modeling.std_rules import (
    _std_z, std_part_defaults, guess_std_rule, sanitize_std_rule, _rule_usable,
    _unusable_names, discover_std_parts, merge_std_rules, anchors_overflow,
    dk_fallback_rules, dk_located_names
)
from cad3d.modeling.stdparts import (
    _bool_feature, _place_delta, _rot_xy, _batch_delete, _group_bool_plan,
    scan_model_bodies, anchors_from_offsets, parse_anchor_off,
    group_anchor_instances
)
from cad3d.modeling.nozzle_len import (
    is_nozzle, plan_shift, pick_faces, next_step, nearest_anchor_len,
    plane_span
)
from cad3d.core.guide import GUIDE_LINES, print_guide
from cad3d.modeling.nx_compat import _matrix3x3
from cad3d.modeling.mold_cut import (
    _any_point_inside, _bbox_overlap, _body_matches_bbox, _broken_holes,
    _extents, _grow, _hole_rows, _is_sliver, _kw_hits, _merge_face_bboxes,
    _pair_hits, _pick_points, _rule_for
)
from cad3d.core.constants import (MOLD_AUDIT_VOLUME, MOLD_BBOX_TOL,
                                  MOLD_CUT_RULES, MOLD_TRIAL_CUT)
from cad3d.modeling.extrude import (
    modeling_ents, build_layer, _merge_groups, _merge_note,
    _merge_extrude_enabled
)
from cad3d.ui.dlx_builder import (
    _blk_enum, build_dlx, build_selection_dlx, build_std_dlx, _group_item,
    _blk_label, build_replace_map_dlx
)
from cad3d.ui.dialogs import _BlockDialogBase
from cad3d.selftest.sample_dxf import make_sample_dxf

import cad3d.core.state as _mod_state
import cad3d.modeling.std_rules as _mod_std_rules


def _undefined_name_check(path):
    """AST 静态检查: 模块内所有 Name 引用是否可解析(模块级/内建/作用域链)。"""
    with io.open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    module_names = set(dir(builtins)) | {"__name__", "__file__"}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                module_names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                module_names.add(a.asname or a.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        module_names.add(n.id)

    bad = []

    def fn_locals(fn):
        local = set()
        globs = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                local.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                local.add(n.name)
            elif isinstance(n, ast.arg):
                local.add(n.arg)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                local.add(n.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    local.add(a.asname or a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    local.add(a.asname or a.name)
            elif isinstance(n, ast.Global):
                globs.update(n.names)
        return local, globs

    def visit_fn(fn, enclosing):
        local, globs = fn_locals(fn)
        visible = enclosing | local | globs
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                    and n.id not in visible:
                bad.append("line %d: %s" % (n.lineno, n.id))
        for child in ast.walk(fn):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and child is not fn:
                visit_fn(child, visible)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit_fn(node, module_names)
    return bad


def selftest(dxf_path=None):
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            ok = False

    for _note in _CFG_NOTES:
        print("[INFO] 配置提示: %s" % _note)

    _src = os.path.join(script_dir(), "nx_extrude_runner.py")
    if os.path.isfile(_src):
        bad_names = _undefined_name_check(_src)
        check("AST 未定义名称=0", not bad_names, "; ".join(bad_names[:6]))

    # 1. 链环: 闭合矩形
    segs = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
            DXLine((10, 5), (0, 5)), DXLine((0, 5), (0, 0))]
    closed, opens = find_chains(segs)
    check("矩形闭链", len(closed) == 1 and not opens)

    # 2. 开口链
    segs2 = segs[:3]
    closed2, opens2 = find_chains(segs2)
    check("开口链检测", not closed2 and len(opens2) == 1)

    # 3. 嵌套: 外方 + 内方 → 1 轮廓带 1 孔
    outer = [DXLine((0, 0), (100, 0)), DXLine((100, 0), (100, 100)),
             DXLine((100, 100), (0, 100)), DXLine((0, 100), (0, 0))]
    inner = [DXLine((40, 40), (60, 40)), DXLine((60, 40), (60, 60)),
             DXLine((60, 60), (40, 60)), DXLine((40, 60), (40, 40))]
    profs, opens3, _ = organize_loops(outer + inner)
    check("嵌套→孔", len(profs) == 1 and len(profs[0]["holes"]) == 1,
          "profiles=%d holes=%d" % (len(profs), len(profs[0]["holes"]) if profs else -1))

    # 3b. 三层嵌套(孔中岛)
    def _sq(x, y, w, h):
        return [DXLine((x, y), (x + w, y)), DXLine((x + w, y), (x + w, y + h)),
                DXLine((x + w, y + h), (x, y + h)), DXLine((x, y + h), (x, y))]

    _A, _B, _C = _sq(0, 0, 100, 100), _sq(20, 20, 60, 60), _sq(40, 40, 20, 20)
    profs3b, _o3b, _ = organize_loops(_A + _B + _C)
    check("三层嵌套: 岛独立成轮廓(不并进孔)",
          len(profs3b) == 2 and len(profs3b[0]["holes"]) == 1
          and not profs3b[1]["holes"]
          and profs3b[0]["outer"]["bbox"] == (0, 0, 100, 100)
          and profs3b[1]["outer"]["bbox"] == (40, 40, 60, 60),
          "profiles=%d" % len(profs3b))

    # 3c. 四层嵌套
    _D = _sq(10, 10, 80, 80)
    profs3c, _o3c, _ = organize_loops(_A + _D + _B + _C)
    check("四层嵌套: 外带1孔 + 岛带1孔",
          len(profs3c) == 2 and len(profs3c[0]["holes"]) == 1
          and len(profs3c[1]["holes"]) == 1
          and profs3c[1]["outer"]["bbox"] == (20, 20, 80, 80),
          "profiles=%d" % len(profs3c))

    # 4. 圆独立轮廓 + 弧参与闭环
    arc_ring = [DXArc((50, 50), 20, 0, math.pi), DXArc((50, 50), 20, math.pi, 2 * math.pi)]
    profs4, _o4, nc4 = organize_loops(arc_ring + [DXCircle((0, 0), 5)])
    check("两半弧成环 + 圆轮廓", len(profs4) == 2)

    # 5. 合成 DXF 解析
    sample = os.path.join(_logs_dir(), "sample_layers.dxf")
    make_sample_dxf(sample)
    layers, stats = parse_dxf(sample)
    check("合成 DXF 各层曲线数",
          len(layers.get("FLB", [])) == 8 and len(layers.get("LS", [])) == 4
          and len(layers.get("DP", [])) == 8 and len(layers.get("RZ", [])) == 2,
          str({k: len(v) for k, v in layers.items()}))
    check("JRT 参考图层导入", len(layers.get("JRT", [])) == 4)
    check("LD 参考图层导入", len(layers.get("LD", [])) == 1)
    check("JRTFBX 标记层导入(1 条与 JRT 线重合 + 1 条独立短线)",
          len(layers.get("JRTFBX", [])) == 2)
    mp = assign_layers(["LD", "0", "FLB", "JRT", "JRTFBX"])
    check("动态图层号分配", mp["FLB"] == _cfg("NX_LAYER_START", 101)
          and mp["JRT"] == _cfg("NX_LAYER_JRT", 118)
          and mp["JRTFBX"] == _cfg("NX_LAYER_JRTFBX", 119)
          and mp["0"] == _cfg("NX_LAYER_DYNAMIC_START", 120)
          and mp["LD"] == _cfg("NX_LAYER_DYNAMIC_START", 120) + 1,
          str(mp))

    # 验证图层冲突智能避让
    class _MockCurve(object):
        def __init__(self, layer):
            self.Layer = layer

    class _MockPart(object):
        def __init__(self, occupied_layers):
            self.Curves = [_MockCurve(ly) for ly in occupied_layers]
            self.Bodies = []
            self.Points = []
            self.Sketches = []

    _mock_part = _MockPart([101, 105])
    _avoid_log = []
    _mp_avoid = assign_layers(["FLB", "JT", "JRT", "0"], work_part=_mock_part, log=lambda m: _avoid_log.append(m))
    check("图层冲突智能自动避让",
          _mp_avoid["FLB"] > 101 and 101 not in _mp_avoid.values()
          and 105 not in _mp_avoid.values() and len(_avoid_log) > 0)

    _lo_cfg = _cfg("LINK_OFFSETS", {})
    if not isinstance(_lo_cfg, dict):
        _lo_cfg = {}
    check("联动/JRT建模/图层号均来自 config(v1.33; v2.13 RZ/DK 出联)",
          _LINK_OFFSETS == {k: _cfg_num(_lo_cfg.get(k), d)
                            for k, d in (("DP", 6.7023),)}
          and JRT_FROM_TOP == _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)
          and DEFAULT_JRT["offset"] == _cfg_num(_cfg("JRT_OFFSET", 5.0), 5.0)
          and DEFAULT_JRT["draft"] == _cfg_num(_cfg("JRT_DRAFT", 2.0), 2.0)
          and DEFAULT_JRT["color_strip"] == _cfg_int("JRT_COLOR_STRIP", 186)
          and MANAGED_MAX == _cfg_int("NX_LAYER_MAX", 170)
          and STDPARTS_DIRNAME == _cfg("STDPARTS_DIRNAME", "stdparts"))

    # 6. 几何指纹
    fp_line = _dxf_ent_fp(DXLine((10.00004, 20.0), (10.0, 25.0)))
    fp_line2 = _dxf_ent_fp(DXLine((10.0, 25.0), (10.00004, 20.0)))
    check("线指纹与端点顺序无关", fp_line == fp_line2)
    fp_c = _dxf_ent_fp(DXCircle((5, 5), 3))
    fp_a = _dxf_ent_fp(DXArc((5, 5), 3, 0.0, 2 * math.pi))
    check("圆指纹=整圆弧指纹(与建法一致)", fp_c == fp_a, "%s vs %s" % (fp_c, fp_a))
    fps = dxf_fingerprints({"X": [DXLine((0, 0), (1, 1)), DXCircle((2, 2), 1)]})
    check("指纹多重集", fps.get(fp_line, 0) == 0 and
          fps.get(("L", (0.0, 0.0), (1.0, 1.0)), 0) == 1 and
          fps.get(_dxf_ent_fp(DXCircle((2, 2), 1)), 0) == 1)

    # 7. JRT 侧向区间
    sides = _jrt_sides(-40.0, -47.5, -85.0)
    check("JRT 两侧区间(负 Z)",
          sides == [("T", -40.0, -47.5), ("B", -85.0, -77.5)], str(sides))
    sides2 = _jrt_sides(45.0, 37.5, 0.0)
    check("JRT 两侧区间(正 Z)",
          sides2 == [("T", 45.0, 37.5), ("B", 0.0, 7.5)], str(sides2))
    jx = merge_jrt({"jrt": {"start": "5", "end": -2.5, "blend_r": 3.8}})
    check("JRT 不读记忆(恒默认)", jx == dict(DEFAULT_JRT), str(jx))
    check("JRT 默认值 3.9/0.1/3.7",
          DEFAULT_JRT["blend_r"] == 3.9 and DEFAULT_JRT["r_step"] == 0.1
          and DEFAULT_JRT["r_min"] == 3.7)

    # 7b. FLB 联动推导
    d = derive_linked(-40.0, -90.0)
    check("联动推导 FLB(-40,-90)",
          d["LS"] == (-40.0, -90.0)
          and abs(d["DP"][0] - -83.2977) < 1e-9 and d["DP"][1] == -90.0
          and d["JRT"] == (-40.0, -47.5), str(d))
    d2 = derive_linked(45.0, 0.0)
    check("联动推导 正 Z 参数",
          d2["DP"] == (6.7023, 0.0) and d2["JRT"] == (45.0, 37.5))
    check("RZ/DK 已解除联动(v2.13): derive_linked 不再输出",
          "RZ" not in d and "DK" not in d and "RZ" not in d2 and "DK" not in d2)

    # 7b-2. JT 联动模式(v1.37)
    check("derive_linked 默认不含 JT",
          "JT" not in derive_linked(-40.0, -85.0))
    check("JT 联动普通模式 FLB(-40,-85)→(-30,-100)",
          _jt_link_values(-40.0, -85.0, "普通模式") == (-30.0, -100.0))
    check("JT 联动针阀模式 FLB(-40,-85)→(-25,-100)",
          _jt_link_values(-40.0, -85.0, "针阀模式") == (-25.0, -100.0))
    check("derive_linked 带 jt_mode 输出 JT",
          derive_linked(-40.0, -85.0, jt_mode="针阀模式")["JT"]
          == (-25.0, -100.0))
    check("CX 联动: 起始=JT起始, 结束=起始-35",
          _cx_link_values(-30.0) == (-30.0, -65.0))
    check("CX 联动示例: 起始-25 → 结束-60",
          _cx_link_values(-25.0) == (-25.0, -60.0))
    dp = default_params()
    check("兜底 FLB -40/-85", dp["FLB"] == (-40.0, -85.0))
    check("兜底联动层推导(普通模式)",
          dp["JT"] == (-30.0, -100.0) and dp["CX"] == (-30.0, -65.0)
          and dp["RZ"] == (0.0, 0.0) and dp["DK"] == (0.0, 0.0)
          and dp["LS"] == (-40.0, -85.0) and dp["DP"][0] == -78.2977)
    check("RZ/DK 默认 0/0 = 不做(v2.13)",
          dp["RZ"] == (0.0, 0.0) and dp["DK"] == (0.0, 0.0))
    check("jt 模式记忆恢复", jt_mode_with_memory(
        {"jt_link_mode": "针阀模式"}) == "针阀模式")
    check("jt 模式记忆无效回默认",
          jt_mode_with_memory({"jt_link_mode": "不存在"}) == JT_LINK_DEFAULT)
    check("jt 模式无记忆回默认", jt_mode_with_memory({}) == JT_LINK_DEFAULT)
    check("窗口② dlx 含 JT 联动下拉",
          "jt_link" in build_dlx(default_params(), dict(DEFAULT_JRT),
                                 jt_mode="普通模式"))

    # 7b-2. 镜像(v2.5 定案): 仅把 FLB 取负保序翻侧(-40/-85→40/85, 用户定案),
    #       其余按常规联动公式整体重推=手输等效(同一设计搬到另一侧, 各特征
    #       角色面不变)。不得把全部层逐个取负(初版方案, 已否): ZMODE TOP/
    #       BOTTOM 与 JRT 齐平/嵌入端都按数值大小定向, 全取负会把热咀/压线
    #       板/加热条翻到对面板面、B 侧压条跑出板外(2026-09-09 用户实测)。
    _mt, _mb = 85.0, 40.0                  # 翻转后 FLB(40,85) 的 max/min
    _mlink = derive_linked(_mt, _mb, jt_mode="普通模式")
    check("镜像口径: FLB 翻 40/85 后常规联动(=手输等效)",
          _mlink["LS"] == (85.0, 40.0)
          and _mlink["DP"] == (46.7023, 40.0)
          and _mlink["JT"] == (95.0, 25.0) and _mlink["JRT"] == (85.0, 77.5)
          and _cx_link_values(_mlink["JT"][0]) == (95.0, 60.0))
    _sides_p = _jrt_sides(_mlink["JRT"][0], _mlink["JRT"][1], _mb)
    check("镜像口径: 加热条两压条齐平面均贴板面(40/85 板)",
          _sides_p == [("T", 85.0, 77.5), ("B", 40.0, 47.5)], str(_sides_p))
    check("窗口② dlx 含镜像按钮",
          'id="flb_mirror"' in build_dlx(default_params(), dict(DEFAULT_JRT)))

    # 7c. enum Value 属性写入选中序号
    en = _blk_enum("t", "测试", ["甲", "乙", "丙"], 2)
    check("enum Value=选中序号", 'sname="TEMPVALUE" source="1" type="integer" value="2"'
          in en)
    xml3 = build_dlx(default_params(), dict(DEFAULT_JRT))
    try:
        ET.fromstring(xml3)
        check("带 JRT dlx 良构", True)
    except ET.ParseError as ex:
        check("带 JRT dlx 良构", False, str(ex))
    check("dlx jrt 块数=5+重置按钮",
          xml3.count('type="string" value="jrt_') == 6
          and 'id="jrt_reset"' in xml3)
    check("RetainValue 全 False(防跨窗保留污染)",
          'sname="RetainValue" source="1" type="logical" value="True"' not in xml3)
    for _nm, _xx in (("标准件参数dlx", build_std_dlx({}, default_params())),
                     ("选件dlx", build_selection_dlx(["a.prt"], []))):
        check("RetainValue False(%s)" % _nm,
              'sname="RetainValue" source="1" type="logical" value="True"'
              not in _xx)
    _fp = _fresh_dlx_path("selftest_dlx")
    check("dlx 唯一名( NX 旧值记忆无载体)",
          "selftest_dlx_" in os.path.basename(_fp)
          and not os.path.isfile(_fp))

    for key, _label in JRT_FIELDS:
        check("JRT id 往返 jrt_%s" % key,
              ('value="jrt_%s"' % key) in xml3)

    # 7d. 标准件规则引擎
    g1 = guess_std_rule("垫片.prt")
    check("猜测: 垫片→DK/FLB顶/放置+减去", g1["layer"] == "DK"
          and g1["z_mode"] == "FLB_TOP" and g1["bool_mode"] == "PLACE_SUBTRACT")
    g2 = guess_std_rule("大水口-25.prt")
    check("猜测: 大水口→RZ/FLB底/放置+减去(v2.13)", g2["layer"] == "RZ"
          and g2["z_mode"] == "FLB_BOTTOM"
          and g2["bool_mode"] == "PLACE_SUBTRACT")
    check("猜测: 热咀族布尔默认放置+减去(v2.13)",
          guess_std_rule("点胶口-18.prt")["bool_mode"] == "PLACE_SUBTRACT"
          and guess_std_rule("热咀big.prt")["bool_mode"] == "PLACE_SUBTRACT"
          and guess_std_rule("Nozzle-30.prt")["bool_mode"] == "PLACE_SUBTRACT")
    g3 = guess_std_rule("LS-45.prt")
    check("猜测: LS-→LS/FLB顶/放置+减去", g3["layer"] == "LS"
          and g3["z_mode"] == "FLB_TOP"
          and g3["bool_mode"] == "PLACE_SUBTRACT")
    g4 = guess_std_rule("主进胶与中心定位垫片-30.prt")
    check("猜测: 主进胶优先于垫片/DP/FLB底/放置+减去",
          g4["layer"] == "DP" and g4["z_mode"] == "FLB_BOTTOM"
          and g4["bool_mode"] == "PLACE_SUBTRACT")
    check("旧字段已删(bool_body/ref_*/anchor)",
          "bool_body" not in g3 and "ref_x" not in g3 and "anchor" not in g3)
    g7 = guess_std_rule("接线盒-24针.prt")
    check("猜测: 接线盒→CXK线中点/CX顶值/仅放置",
          g7["layer"] == "CXK" and g7["z_mode"] == "CX_TOP"
          and g7["bool_mode"] == "PLACE")
    check("CXK 在图层选项且规则合法",
          "CXK" in [v for v, _t in LAYER_SEL_OPTS]
          and sanitize_std_rule({"layer": "cxk"})["layer"] == "CXK")
    lay_k = {"CXK": [DXLine((4508.8388106206, 1791.264313510919),
                            (4543.782447818045, 1789.27881120337))]}
    ak = collect_circle_anchors(lay_k, sanitize_std_rule({"layer": "CXK"}))
    check("CXK 线中点锚点≈(4526.31,1790.27)(3Dtest 实线)",
          len(ak) == 1 and abs(ak[0][0] - 4526.3106) < 0.01
          and abs(ak[0][1] - 1790.2716) < 0.01, str(ak))

    # 7d-2. 一键替换: 体类型标记扫描(只收脚本产物, 用户图形不碰)

    class _MockMarkedBody:
        def __init__(self, type_str):
            self._t = type_str

        def GetStringAttribute(self, name):
            return self._t if name == "CAD3D_TYPE" else ""

    class _MockScanPart:
        def __init__(self, bodies):
            self.Bodies = bodies

    _scan_rows = scan_model_bodies(
        _MockScanPart([_MockMarkedBody("STD:大水口-18.prt"),
                       _MockMarkedBody("FLB"),
                       _MockMarkedBody("")]), None)
    check("扫描: 只收带 CAD3D_TYPE 标记的体(用户图形不碰)",
          len(_scan_rows) == 2
          and [r[0] for r in _scan_rows] == ["STD:大水口-18.prt", "FLB"],
          str([r[0] for r in _scan_rows]))
    check("扫描: 离线拿不到 UF 时包围盒为 None(不崩不中断)",
          all(r[2] is None for r in _scan_rows))

    # 7d-3. 一键替换 v3: 体上记的锚点 → 实例放置点 + 映射页(2026-09-18 改口径)
    # v3.3(用户 2026-09-18 定案): 锚点存**绝对坐标** + 记时的体中心 + 角度(7 个数)。
    # 旧版 4 个数是"锚点−体中心"的偏移, 仍要能读(老模型兼容)。
    check("锚点记录解析: 7 数(绝对锚点+记时体中心+角度)",
          parse_anchor_off("100,50,-85,10,5,-131,90")
          == ((100.0, 50.0, -85.0), (10.0, 5.0, -131.0), 90.0))
    check("锚点记录解析: 旧 4 数(偏移)仍能读, 体中心记 None",
          parse_anchor_off("12.5,-3,45,90") == ((12.5, -3.0, 45.0), None, 90.0)
          and parse_anchor_off("1,2,3") == ((1.0, 2.0, 3.0), None, 0.0))
    check("锚点记录解析: 空/坏值/字段不足都回 None",
          parse_anchor_off("") is None and parse_anchor_off("a,b,c") is None
          and parse_anchor_off("1,2") is None and parse_anchor_off(None) is None)

    def _bb_of(c, half=1.0):
        return (c[0] - half, c[1] - half, c[2] - half,
                c[0] + half, c[1] + half, c[2] + half)

    # 一个 7 实体件(含两颗小螺丝)放在 (100,50,-85): 每体都记同一个**绝对锚点**
    _anchor = (100.0, 50.0, -85.0)
    _centers = [(100.0, 50.0, -85.0), (100.0, 50.0, -115.0),
                (103.0, 50.0, -85.0), (100.0, 47.0, -85.0),
                (100.0, 50.0, -55.0), (106.0, 50.0, -85.0),
                (100.0, 56.0, -85.0)]
    _items = [(_bb_of(c),
               parse_anchor_off("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,0"
                                % (_anchor[0], _anchor[1], _anchor[2],
                                   c[0], c[1], c[2])))
              for c in _centers]
    _anch, _miss = anchors_from_offsets(_items)
    check("反推锚点: 7 个实体(含尺寸重样的)归成 1 处实例",
          len(_anch) == 1 and _miss == 0, str(_anch))
    check("反推锚点: 精确还原(不用认实体、不用图纸)",
          abs(_anch[0][0] - 100.0) < 1e-9 and abs(_anch[0][1] - 50.0) < 1e-9
          and abs(_anch[0][2] + 85.0) < 1e-9, str(_anch))
    check("反推锚点: 角度跟着记录走(压线板摆向不丢)",
          anchors_from_offsets([(_bb_of((0.0, 0.0, 0.0)),
                                 parse_anchor_off("5,6,7,0,0,0,33"))])[0][0][3]
          == 33.0)

    # v3.3 的取舍: 锚点是**绝对坐标** ⇒ 件被手动挪走后锚点**不动**(不再跟随)。
    # 用户 2026-09-18 明确要求"锚点永远一样, 不随长度改变而改变" —— 长度/几何
    # 一变就漂是实机偏移的根因, 所以这里选了"绝对不变"。
    _dx, _dy = 54.0, -39.0
    _moved = [((bb[0] + _dx, bb[1] + _dy, bb[2], bb[3] + _dx, bb[4] + _dy,
               bb[5]), rec) for (bb, rec) in _items]
    _anch_m, _miss_m = anchors_from_offsets(_moved)
    check("反推锚点: v3.3 绝对锚点 → 件被挪走后锚点也不动",
          len(_anch_m) == 1 and _miss_m == 0
          and abs(_anch_m[0][0] - 100.0) < 1e-9
          and abs(_anch_m[0][1] - 50.0) < 1e-9, str(_anch_m))

    # 关键回归(用户正是这么撞上的): **件被拉长/缩短后锚点必须纹丝不动**
    _rec_one = parse_anchor_off("1046.745,-46.859,-85,5,5,-131,0")
    _a_ok = anchors_from_offsets([((0.0, 0.0, -190.0, 10.0, 10.0, -72.0),
                                   _rec_one)])[0][0]
    _a_long = anchors_from_offsets([((0.0, 0.0, -210.0, 10.0, 10.0, -72.0),
                                     _rec_one)])[0][0]
    check("反推锚点: 件拉长 20mm 后锚点一模一样(不再漂)",
          _a_ok[:3] == (1046.745, -46.859, -85.0) and _a_long[:3] == _a_ok[:3],
          "%r vs %r" % (_a_ok, _a_long))
    check("反推锚点: 旧格式(只有偏移)仍按体中心换算 —— 老模型兼容",
          abs(anchors_from_offsets(
              [((0.0, 0.0, -210.0, 10.0, 10.0, -72.0),
                parse_anchor_off("0,0,50,0"))])[0][0][2] + 91.0) < 1e-9)

    _three = list(_items) + [
        ((bb[0] + 200.0, bb[1] + 150.0, bb[2],
          bb[3] + 200.0, bb[4] + 150.0, bb[5]),
         parse_anchor_off("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,0"
                          % (_anchor[0] + 200.0, _anchor[1] + 150.0,
                             _anchor[2], c[0] + 200.0, c[1] + 150.0, c[2])))
        for (bb, _r), c in zip(_items, _centers)]
    _anch2, _miss2 = anchors_from_offsets(_three)
    check("反推锚点: 同件放两处 → 2 处实例(不会少也不会多)",
          len(_anch2) == 2 and _miss2 == 0, str(_anch2))

    _anch3, _miss3 = anchors_from_offsets(
        list(_items) + [(_bb_of((300.0, 300.0, -85.0)), None)])
    check("反推锚点: 没记录的体计入缺记录(调用方不动它)",
          len(_anch3) == 1 and _miss3 == 1, "%r %r" % (_anch3, _miss3))
    check("反推锚点: 全部没记录 → 无锚点、全计缺记录",
          anchors_from_offsets([(_bb_of((0.0, 0.0, 0.0)), None)]) == ([], 1))
    check("反推锚点: 空输入安全",
          anchors_from_offsets([]) == ([], 0)
          and anchors_from_offsets(None) == ([], 0))

    _rmx = build_replace_map_dlx(["大水口-25.prt", "接线盒-48针.prt"],
                                 ["大水口-18.prt", "大水口-25.prt"],
                                 {"大水口-25.prt": "大水口-18.prt"})
    check("映射页: 每个旧件一行, 候选含“不替换”+全部规格",
          _rmx.count('id="MAP0"') >= 1 and _rmx.count('id="MAP1"') >= 1
          and "不替换" in _rmx and "大水口-18.prt" in _rmx)
    check("映射页: 上次的映射写进 selected 序号(记忆回填)",
          'selected="1"' in _rmx and "没选的标准件不会被改动" in _rmx)
    check("映射页: 空旧件列表也生成良构 XML",
          "Dialog" in build_replace_map_dlx([], ["a.prt"], None)
          and "当前模型里没有标准件" in build_replace_map_dlx([], [], None))

    # 7d-4. 热咀替换长度对齐(v3.2): 按高度选面 + 就地移面, 总长=旧件
    check("热咀族判定: 大水口/点胶口/热咀/nozzle 命中, 其余不命中",
          is_nozzle("大水口-25.prt") and is_nozzle("点胶口-18.prt")
          and is_nozzle("热咀x.prt") and is_nozzle("Nozzle-30.prt")
          and not is_nozzle("螺丝-45.prt") and not is_nozzle("接线盒-24针.prt")
          and not is_nozzle("") and not is_nozzle(None))
    # 两体件: 头部 -60..-30(顶带30), 咀身 -100..-61(全在头部带以下)
    _nz_head = (0.0, 0.0, -60.0, 10.0, 10.0, -30.0)
    _nz_tip = (0.0, 0.0, -100.0, 8.0, 8.0, -61.0)
    _nsh, _cut, _nt = plan_shift(60.0, [_nz_head, _nz_tip], 1)
    check("长度对齐: 新件长70旧件60 → 沿 Z +10(缩短), 分界在 -60",
          abs(_nsh - 10.0) < 1e-9 and abs(_cut + 60.0) < 1e-9 and _nt == "",
          "%r %r %r" % (_nsh, _cut, _nt))
    _nsh2, _cut2, _nt2 = plan_shift(80.0, [_nz_head, _nz_tip], 1)
    check("长度对齐: 新件比旧件短 → 沿 Z -10(往下拉长)",
          abs(_nsh2 + 10.0) < 1e-9 and abs(_cut2 + 60.0) < 1e-9)
    _nsh3, _cut3, _nt3 = plan_shift(70.0, [_nz_head, _nz_tip], 1)
    check("长度对齐: 新旧等长免调", _nsh3 is None and "等长" in _nt3)
    # 短头(5mm)两体件: 咀身伸进顶部带 → 只带以下的面入选
    _nz_sh_head = (0.0, 0.0, -35.0, 10.0, 10.0, -30.0)
    _nz_sh_tip = (0.0, 0.0, -60.0, 8.0, 8.0, -34.0)
    _nsh4, _cut4, _nt4 = plan_shift(40.0, [_nz_sh_head, _nz_sh_tip], 1)
    check("长度对齐: 头很短时照旧给得出移面量(不再需要手动)",
          abs(_nsh4 + 10.0) < 1e-9 and abs(_cut4 + 60.0) < 1e-9 and _nt4 == "",
          "%r %r %r" % (_nsh4, _cut4, _nt4))
    # -Z 干净路径: 头 -100..-70(底带30), 咀身 -60..-40
    _nz_head_f = (0.0, 0.0, -100.0, 10.0, 10.0, -70.0)
    _nz_tip_f = (0.0, 0.0, -60.0, 8.0, 8.0, -40.0)
    _nsh5, _cut5, _nt5 = plan_shift(70.0, [_nz_head_f, _nz_tip_f], -1)
    check("长度对齐: -Z 新件短10 → 沿 Z +10(往上提), 分界在 -70",
          abs(_nsh5 - 10.0) < 1e-9 and abs(_cut5 + 70.0) < 1e-9 and _nt5 == "")
    _nsh6, _cut6, _nt6 = plan_shift(60.0, [_nz_head], 1)
    check("长度对齐: 单实体也能拉长(移它的底面), 不再束手无策",
          abs(_nsh6 + 30.0) < 1e-9 and abs(_cut6 + 60.0) < 1e-9 and _nt6 == "")
    _nsh7, _cut7, _nt7 = plan_shift(None, [_nz_head, _nz_tip], 1)
    check("长度对齐: 旧件长度缺 → 不调", _nsh7 is None and "没找到" in _nt7)
    _nsh8, _cut8, _nt8 = plan_shift(60.0, [_nz_head, _nz_tip, None], 1)
    check("长度对齐: 包围盒读不到 → 不调", _nsh8 is None and "包围盒" in _nt8)

    # 选面: 只要"水平面"(朝上/朝下): 移它才有几何意义; 侧壁一律不选 —— 沿轴向
    # 平移侧壁 NX 给不出干净几何, 长度也就对不准(用户反馈"总有一些差距"的根因)。
    # 侧壁交给 NX 自己延伸, 与用户录制日记里"只手选 4 块朝上/朝下的面"一致。
    _fb = [(0.0, 0.0, -100.0, 8.0, 8.0, -100.0),    # 咀尖底面(水平)
           (0.0, 0.0, -100.0, 8.0, 8.0, -61.0),     # 咀尖侧面(整块在带下→仍不选)
           (0.0, 0.0, -60.0, 10.0, 10.0, -60.0),    # 头部底面(恰在分界, 水平)
           (0.0, 0.0, -60.0, 10.0, 10.0, -30.0)]    # 头部侧面(跨带→不动)
    check("选面: 只要带以下的水平面(底面入选, 侧面不选)",
          pick_faces(_fb, -60.0, 1) == [0, 2], str(pick_faces(_fb, -60.0, 1)))
    check("选面: 宽口径保底(一个水平面都没有时退回带以下的面)",
          pick_faces(_fb, -60.0, 1, flat_only=False) == [0, 1, 2])
    check("选面: -Z 翻转按底带判(Z 低端在界以上的才动)",
          pick_faces([(0.0, 0.0, -70.0, 1.0, 1.0, -70.0),
                      (0.0, 0.0, -100.0, 1.0, 1.0, -60.0)], -70.0, -1) == [0])
    check("选面: 空/坏输入安全",
          pick_faces([], -60.0, 1) == [] and pick_faces(None, -60.0, 1) == []
          and pick_faces([None], -60.0, 1) == [])
    # 迭代步长(移面 → 复测 → 再移): 返回的是**带符号的移面量**(往下为负),
    # 符号错会越移越远, 单独测。头在顶时"往下移 = 变长" ⇒ 短了给负、长了给正。
    check("移面步长: 头在顶, 短了往下移(负)/ 长了往上移(正)",
          next_step(100.0, 80.0, 1) == -20.0 and next_step(100.0, 120.0, 1) == 20.0)
    check("移面步长: -Z 翻转(头在底)时符号相反",
          next_step(100.0, 80.0, -1) == 20.0 and next_step(100.0, 120.0, -1) == -20.0)
    check("移面步长: 够准/坏输入都返回 0(停止迭代)",
          next_step(100.0, 100.03, 1) == 0.0 and next_step(None, 80.0, 1) == 0.0
          and next_step(100.0, None, 1) == 0.0)
    # 长度口径(用户 2026-09-18 定案): 顶/底取**主平面** —— 朝上的平面里 z 最高的、
    # 朝下的平面里 z 最低的; 顶上的小凸起若是曲面, 天然落不进"平面"。
    # 真实数据(NX2312 实测): 点胶口-18 顶面是 13.0000 的平面, 但几何最高点是
    # 13.2043 的**曲面**凸台 → 用户量 95.9673 = 13.0000-(-82.9673), 脚本必须同值。
    def _fr(zlo, zhi, nz, flat=True):
        return ((0.0, 0.0, zlo, 1.0, 1.0, zhi), nz, flat, None)

    _rows18 = [_fr(13.0, 13.0, 1.0),           # 主体顶面(平面朝上)
               _fr(-0.0, -0.0, 1.0),           # 台阶
               _fr(-15.0, -15.0, 1.0),         # 另一体的顶面
               _fr(-64.6173, -64.6173, -1.0),  # 朝下的面
               _fr(-82.9673, -82.9673, -1.0)]  # 最低的朝下面
    _sp_top, _sp_bot, _sp_how = plane_span(
        _rows18, (0.0, 0.0, -82.9673, 1.0, 1.0, 13.2043))
    check("长度口径: 顶=朝上平面里最高的, 底=朝下平面里最低的",
          abs(_sp_top - 13.0) < 1e-9 and abs(_sp_bot + 82.9673) < 1e-9,
          "%r %r" % (_sp_top, _sp_bot))
    check("长度口径: 点胶口-18 得出用户那个 95.9673(而非包围盒 96.1716)",
          abs((_sp_top - _sp_bot) - 95.9673) < 1e-6,
          "%.4f" % (_sp_top - _sp_bot))
    check("长度口径: 曲面凸起(非平面)不参与",
          plane_span([_fr(13.2043, 13.2043, 1.0, flat=False),
                      _fr(13.0, 13.0, 1.0),
                      _fr(-82.9673, -82.9673, -1.0)], None)[0] == 13.0)
    check("长度口径: 一侧没平面 → 那侧退回包围盒",
          plane_span([_fr(13.0, 13.0, 1.0)],
                     (0.0, 0.0, -50.0, 1.0, 1.0, 99.0))[:2] == (13.0, -50.0))
    check("长度口径: 一个平面都没有 → 纯包围盒",
          plane_span([_fr(0.0, 0.0, 0.5, flat=False)],
                     (0.0, 0.0, -7.0, 1.0, 1.0, 3.0))[:2] == (3.0, -7.0))
    check("长度口径: 空/坏输入安全",
          plane_span([], None)[0] is None
          and plane_span(None, None)[0] is None
          and plane_span([None], None)[0] is None)
    _sh_sp, _cut_sp, _nt_sp = plan_shift(
        95.9673, [(0.0, 0.0, -100.0, 1.0, 1.0, 13.2043)], 1, span=(13.0, -95.0))
    check("长度口径: plan_shift 认 span(新件 108 → 缩短 12.0327, 分界 -17)",
          abs(_sh_sp - 12.0327) < 1e-3 and abs(_cut_sp + 17.0) < 1e-9
          and _nt_sp == "", "%r %r %r" % (_sh_sp, _cut_sp, _nt_sp))
    check("长度口径: 不传 span 仍是旧行为(包围盒)",
          plan_shift(96.1716, [(0.0, 0.0, -82.9673, 1.0, 1.0, 13.2043)],
                     1)[2].startswith("新旧等长"))

    # 定位点守恒(用户 2026-09-18 定案): 件上"定位点"= 某个面的圆心, 必须永远落在
    # 放置点上 ⇒ 那个高度绝不能进移面范围。分界取"头部带"与它之间更严的那个。
    _pb = [(0.0, 0.0, -120.0, 1.0, 1.0, 10.0)]      # top=10 → 头部带底 = -20
    check("定位点守恒: 放置点高度比头部带更靠上时, 取头部带(不变)",
          plan_shift(100.0, _pb, 1, fix_z=5.0)[1] == -20.0)
    check("定位点守恒: 放置点高度更低时, 分界收窄到它(定位面以上一律不动)",
          plan_shift(100.0, _pb, 1, fix_z=-40.0)[1] == -40.0)
    check("定位点守恒: -Z 翻转时取更高的那个分界",
          plan_shift(100.0, [(0.0, 0.0, -30.0, 1.0, 1.0, 60.0)], -1,
                     fix_z=20.0)[1] == 20.0)
    check("定位点守恒: 不给 fix_z 仍是旧行为(只看头部带)",
          plan_shift(100.0, _pb, 1, fix_z=None)[1] == -20.0)

    # 回归(2026-09-18): 实机"移完异形"的根因是**运动参数没照日记设全** ——
    # 只设 DeltaXyz 三项不够, NX 会沿用方向/曲线模式, 移出来不是纯平移。
    # 这类"参数遗漏"只能靠源码守门(离线跑不了 NX)。
    with io.open(sys.modules["cad3d.modeling.nozzle_len"].__file__,
                 encoding="utf-8") as _nl_f:
        _nl_src = _nl_f.read()
    check("移面: 运动参数照日记设全(漏设 = 实机异形)",
          "_tune_motion(bld.Motion, NXOpen)" in _nl_src
          and "FindGeneralClone" in _nl_src
          and "VirtualFaceCollector" in _nl_src
          and "OrientXpress" in _nl_src
          and "AlongCurveAngle" in _nl_src)

    check("长度对齐: 按锚点找旧件长度(容差内命中/miss回None)",
          nearest_anchor_len((100.0, 50.0, -85.0),
                             [((100.0, 50.0, -85.0, 0.0), 60.0)]) == 60.0
          and nearest_anchor_len((100.05, 50.0, -85.0),
                                 [((100.0, 50.0, -85.0, 0.0), 60.0)]) == 60.0
          and nearest_anchor_len((200.0, 50.0, -85.0),
                                 [((100.0, 50.0, -85.0, 0.0), 60.0)]) is None)

    # 旧件体按锚点归实例 + 每实例长度(热咀对齐的数据源)
    def _bbz(zmin, zmax, x=100.0):
        return (x, 50.0, zmin, x, 50.0, zmax)

    def _rec_at(ax, ay, az, cx, cy, cz):
        return parse_anchor_off("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,0"
                                % (ax, ay, az, cx, cy, cz))

    _old_items = [
        (_bbz(-70.0, -40.0), _rec_at(100.0, 50.0, -85.0, 100.0, 50.0, -55.0)),
        (_bbz(-120.0, -80.0), _rec_at(100.0, 50.0, -85.0, 100.0, 50.0, -100.0)),
        (_bbz(-70.0, -40.0, x=300.0),
         _rec_at(300.0, 50.0, -85.0, 300.0, 50.0, -55.0)),
        (None, _rec_at(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),   # 坏记录不进组
    ]
    _grp = group_anchor_instances(_old_items)
    check("旧件分实例: 同锚点归同组, 坏记录不进组",
          len(_grp) == 2 and sorted(len(g[1]) for g in _grp) == [1, 2]
          and _grp[0][0][:3] == (100.0, 50.0, -85.0), str(_grp))
    check("旧件分实例: 空输入安全", group_anchor_instances([]) == []
          and group_anchor_instances(None) == [])

    # 回归(2026-09-18): 放置钩子(会改几何 = 移面对齐)必须跑在记锚点**之前**。
    # 锚点记的是「锚点 − 体中心」, 先记后移面 == 记下的偏移当场过期: 下次替换按
    # 「当前体中心 + 偏移」反推出来的锚点就偏了, 同件的多个体还会算出不重合的锚点
    # 而让归组散架 —— 用户看到的就是"多替换几次后 Z 轴越换越偏、旧件长度也量得
    # 忽长忽短"。顺序靠源码守门, 不能只写在注释里。
    with io.open(sys.modules["cad3d.modeling.stdparts"].__file__,
                 encoding="utf-8") as _sp_f:
        _sp_src = _sp_f.read()
    _sp_seq = []
    for _nd in ast.walk(ast.parse(_sp_src)):
        if isinstance(_nd, ast.Call):
            _nm = getattr(_nd.func, "id", None) or getattr(_nd.func, "attr", None)
            if _nm in ("placed_hook", "_mark_anchor"):
                _sp_seq.append((_nd.lineno, _nm))
    _sp_names = [n for _l, n in sorted(_sp_seq)]
    check("回归: 放置钩子先跑、锚点后记(顺序反了锚点当场过期)",
          _sp_names == ["placed_hook", "_mark_anchor"], str(_sp_names))
    # 同一件事的算术说明: 体中心因移面下移 20, 偏移若按移面前的中心记 → 反推偏 20
    _c_before = (0.0, 0.0, -100.0)
    _c_after = (0.0, 0.0, -120.0)
    _want = (10.0, 5.0, -85.0)
    _off_after = tuple(_want[i] - _c_after[i] for i in range(3))
    _off_before = tuple(_want[i] - _c_before[i] for i in range(3))
    check("回归: 锚点按移面后的体中心记才对(按移面前记会偏 20)",
          tuple(_c_after[i] + _off_after[i] for i in range(3)) == _want
          and tuple(_c_after[i] + _off_before[i] for i in range(3))
          == (10.0, 5.0, -105.0))

    # 三个主入口的大白话说明(v2.13): 每个脚本名真实存在且说明非空
    check("脚本指南: 三个入口都有大白话说明且文件真实存在",
          len(GUIDE_LINES) == 3
          and all(d for _n, d in GUIDE_LINES)
          and all(os.path.isfile(os.path.join(script_dir(), n))
                  for n, _d in GUIDE_LINES))
    _sw = io.StringIO()
    _so = sys.stdout
    try:
        sys.stdout = _sw
        print_guide("nx_std_replace_runner.py")
    finally:
        sys.stdout = _so
    _gtxt = _sw.getvalue()
    check("脚本指南: 启动打印三行说明并标记本次脚本",
          _gtxt.count("\n") >= 4 and "← 本次运行" in _gtxt
          and "建模" in _gtxt and "换件" in _gtxt and "开框" in _gtxt)

    # 7e. YXB 压线板: 贴合边中点锚点 + 逐板轮廓自动判向(26079 前跑板实图定案,
    #     16.6 长边沿槽向落 CX 线上、板体沿背离槽方向, longaxis_deg=0;
    #     2026-09-09 矩阵转置修复后 θ=f: 旧"水平槽壁+180°补偿"是 bug 掩盖
    #     补丁已删——四类墙世界角统一=f, 与实机验证结果一致)
    _yxb_cases = [
        ("板体-Y", [DXLine((-5, 0), (30, 0))],
         [DXLine((0, 0), (10, 0)), DXLine((0, 0), (0, -5))],
         (5.0, 0.0, -90.0)),
        ("板体+Y", [DXLine((-5, 0), (30, 0))],
         [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5))],
         (5.0, 0.0, 90.0)),
        ("板体+X", [DXLine((0, -5), (0, 30))],
         [DXLine((0, 0), (0, 10)), DXLine((0, 10), (5, 10))],
         (0.0, 5.0, 0.0)),
        ("板体-X", [DXLine((0, -5), (0, 30))],
         [DXLine((0, 0), (0, 10)), DXLine((-5, 10), (0, 10))],
         (0.0, 5.0, 180.0)),
    ]
    for _nm, _cxl, _yxl, _exp in _yxb_cases:
        _a, _w = collect_yxb_anchors(_yxl, _cxl)
        check("YXB 判向: %s→θ=%.0f" % (_nm, _exp[2]),
              len(_a) == 1 and not _w
              and abs(_a[0][0] - _exp[0]) < 1e-6
              and abs(_a[0][1] - _exp[1]) < 1e-6
              and abs(_a[0][2] - _exp[2]) < 1e-6, str(_a))
    _a, _w = collect_yxb_anchors(
        [DXLine((0, 0), (10, 0)), DXLine((0, 0), (0, -5)),
         DXLine((15, 0), (25, 0)), DXLine((25, 0), (25, 5))],
        [DXLine((-5, 0), (30, 0))])
    check("YXB 同线双板对向→各自朝向(-90/90)",
          len(_a) == 2 and not _w
          and sorted((round(x, 3), round(y, 3), round(t, 3))
                     for x, y, t in _a) == [(5.0, 0.0, -90.0),
                                            (20.0, 0.0, 90.0)], str(_a))
    _a, _w = collect_yxb_anchors(
        [DXLine((0, 0), (4, 0)), DXLine((6, 0), (10, 0)),
         DXLine((0, 0), (0, -5)), DXLine((0, -5), (10, -5)),
         DXLine((10, -5), (10, 0))],
        [DXLine((-5, 0), (30, 0))])
    check("YXB 贴合边拆两段→并集中点(5,0)+判向-90",
          len(_a) == 1 and not _w and abs(_a[0][0] - 5.0) < 1e-6
          and abs(_a[0][1]) < 1e-6 and abs(_a[0][2] + 90.0) < 1e-6, str(_a))
    _a, _w = collect_yxb_anchors(
        [DXLine((0, 0), (10, 0)), DXLine((0, 0), (0, -5))],
        [DXLine((0, 3), (30, 3))])
    check("YXB CX 平行但不重合(偏距3)→跳过+警告", not _a and len(_w) == 1,
          str(_w))
    _a, _w = collect_yxb_anchors(
        [DXLine((14, 0), (20, 0)), DXLine((14, 0), (14, -5))],
        [DXLine((-5, 0), (15, 0))])
    check("YXB 重叠不足半长→不算贴合边", not _a and len(_w) == 1, str(_a))
    _a, _w = collect_yxb_anchors(
        [DXLine((0, 0), (10, 0)), DXLine((0, 0), (0, -5)),
         DXCircle((30.0, 30.0), 2.0)],
        [DXLine((-5, 0), (30, 0))])
    check("YXB 含圆不崩(圆无端点独立成组仅告警, 板锚点不受影响)",
          len(_a) == 1 and len(_w) == 1
          and abs(_a[0][0] - 5.0) < 1e-6 and abs(_a[0][1]) < 1e-6
          and abs(_a[0][2] + 90.0) < 1e-6, str((_a, _w)))
    _logs = []
    _a = collect_circle_anchors(
        {"YXB": [DXLine((0, 0), (10, 0)), DXLine((0, 0), (0, -5))],
         "CX": [DXLine((-5, 0), (30, 0))]},
        sanitize_std_rule({"layer": "YXB"}), log=_logs.append)
    check("YXB 分支接入: 锚点第三元=角度-90",
          len(_a) == 1 and abs(_a[0][2] + 90.0) < 1e-6, str(_a))
    _a = collect_circle_anchors(
        {"YXB": [DXLine((0, 0), (10, 0))], "CX": []},
        sanitize_std_rule({"layer": "YXB"}), log=_logs.append)
    check("YXB 空 CX→无锚点+警告入日志",
          not _a and any("贴合边" in _s for _s in _logs), str(_logs))
    check("LINE_ANCHOR_LAYERS=CXK+YXB", LINE_ANCHOR_LAYERS == ("CXK", "YXB"))
    check("YXB 在图层选项且规则合法",
          "YXB" in [v for v, _t in LAYER_SEL_OPTS]
          and sanitize_std_rule({"layer": "yxb"})["layer"] == "YXB")
    if _USER_CFG is not None:
        _d = std_part_defaults("压线板.prt")
        check("默认规则: 压线板→YXB/CX顶值", _d is not None
              and _d.get("layer") == "YXB" and _d.get("z_mode") == "CX_TOP",
              str(_d))
    _xml_y = build_std_dlx(
        {"压线板.prt": sanitize_std_rule({"layer": "YXB", "z_mode": "CX_TOP"})},
        default_params())
    check("YXB 件参数页无半径框(与 CXK 同款)",
          "rmin" not in _xml_y and "rmax" not in _xml_y)

    class _FakeNx:
        class Matrix3x3:
            def __init__(self, *vals):
                self.vals = vals

    def _mvals(flip, ang):
        return _matrix3x3(_FakeNx, flip, ang).vals

    check("姿态: θ=0 与旧版逐位一致(+Z/-Z)",
          _mvals(False, 0.0) == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
          and _mvals(True, 0.0) == (1.0, 0.0, 0.0, 0.0, -1.0, 0.0,
                                    0.0, 0.0, -1.0))
    # NX 按传入元素矩阵的转置生效(2026-09-09 实机探针定案): 非翻转分支
    # 传 Rz(−θ) 元素使世界恰为 Rz(+θ); 翻转分支矩阵对称、原值即正确。
    check("姿态: θ=90 非翻转传 Rz(−θ) 元素(NX 转置后世界=Rz+θ)",
          all(abs(a - b) < 1e-12 for a, b in zip(
              _mvals(False, 90.0),
              (0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0)))
          and all(abs(a - b) < 1e-12 for a, b in zip(
              _mvals(True, 90.0),
              (0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, -1.0))))
    check("位移旋转: _rot_xy 90°(1,0)→(0,1) / 0°恒等",
          abs(_rot_xy(1, 0, 90.0)[0]) < 1e-12
          and abs(_rot_xy(1, 0, 90.0)[1] - 1.0) < 1e-12
          and _rot_xy(3, 4, 0.0) == (3, 4))
    _fx = os.path.join(script_dir(), "test", "fixtures", "26079_YXB.dxf")
    if os.path.isfile(_fx):
        _lay, _st = parse_dxf(_fx)
        _ya, _yw = collect_yxb_anchors(_lay.get("YXB") or [],
                                       _lay.get("CX") or [])
        _exp11 = [
            (3582.5, -295.268, 180.0),
            (3582.5, 341.252, 180.0),
            (3661.948, -342.768, -90.0),
            (3661.948, 388.752, 90.0),
            (3811.948, -342.768, -90.0),
            (3811.948, 388.752, 90.0),
            (3891.396, -233.884, 0.0),
            (3891.396, -83.884, 0.0),
            (3891.396, 66.116, 0.0),
            (3891.396, 216.116, 0.0),
            (3891.396, 366.116, 0.0),
        ]
        _got = sorted((round(x, 3), round(y, 3), round(t, 3))
                      for x, y, t in _ya)
        check("真图回归: 26079_YXB 11 板 4 朝向(贴合边中点+自动判向)",
              len(_got) == 11 and not _yw and _got == sorted(_exp11),
              str(_got[:3]))
    else:
        check("真图回归: fixture 缺失跳过(26079_YXB.dxf)", True)

    cx_open = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
               DXLine((10, 5), (0, 5))]
    lay_m = {"CX": cx_open, "CXK": [DXLine((0, 5), (0, 0))]}
    me = modeling_ents(lay_m, "CX")
    profs_m, opens_m, _ = organize_loops(me)
    check("CX+CXK 并入成环", len(me) == 4 and len(profs_m) == 1 and not opens_m)
    check("非 CX 层不并入 CXK",
          len(modeling_ents({"JT": cx_open, "CXK": lay_m["CXK"]}, "JT")) == 3)

    check("护栏: 数量超限", anchors_overflow(
        list(range(201)), sanitize_std_rule({})))
    check("护栏: 正常数量不超限", not anchors_overflow(
        list(range(8)), sanitize_std_rule({"layer": "LS", "r_max": 5})))
    check("护栏: 空图层+大半径=指纹拦截(卡死案规则)",
          anchors_overflow(list(range(47)),
                           sanitize_std_rule({"layer": "", "r_max": 9999})))

    # 开链修复
    _oe = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5)),
           DXLine((0, 5.2), (0.2, 5.2)), DXLine((0.2, 5.2), (0.2, 0.2)),
           DXLine((0.2, 0.2), (0, 0.2))]
    _ce, _bj, _ol = _merge_open_chains(
        [[(0, False), (1, False), (2, False)],
         [(3, False), (4, False), (5, False)]], _oe, tol=0.5, bridge_max=0.5)
    check("开链修复: 近缝两链合并→2条接缝桥(≤0.5)",
          len(_ce) == 0 and len(_bj) == 1 and len(_bj[0][1]) == 2, str(_bj))
    _e2 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5))]
    _ce2, _bj2, _ol2 = _merge_open_chains([[(0, False), (1, False), (2, False)]],
                                          _e2, tol=0.5)
    check("开链修复: 5mm 缺口→放弃记日志(直线桥大缺口=怪条一案)",
          not _ce2 and not _bj2 and len(_ol2) == 1, str((_ce2, _bj2, _ol2)))
    _ce3, _bj3, _ol3 = _merge_open_chains([[(0, False)]], [DXLine((0, 0), (10, 0))],
                                          tol=0.5)
    check("开链修复: 10mm 缺口→放弃", len(_bj3) == 0 and len(_ol3) == 1)

    _e5 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (10, 5.065)), DXLine((10, 5.065), (0, 5.065)),
           DXLine((0, 0.2), (0, 4.8))]
    _ce5, _bj5, _ol5 = _merge_open_chains(
        [[(0, False), (1, False), (2, False), (3, False), (4, False)]],
        _e5, tol=0.5)
    check("开链修复: 两处小缝(0.2/0.265)→2桥闭合",
          not _ce5 and len(_bj5) == 1 and len(_bj5[0][1]) == 2
          and not _ol5, str(_bj5))
    _ce4, _bj4, _ol4 = _merge_open_chains(
        [[(0, False), (1, False), (2, False), (3, False)]],
        [DXLine((0, 0), (5, 0)), DXLine((6, 0), (10, 0)),
         DXLine((0, 1), (5, 1)), DXLine((6, 1), (10, 1))], tol=0.5)
    check("开链修复: 断口>2簇→放弃记日志",
          not _ce4 and not _bj4 and len(_ol4) == 1)

    # 画过头的短线(2026-09-17 RT-26031 实图): 导轨线到切点后又顺原方向多画
    # 一截压回长线, 三岔接点把闭链拆开→整根条不建模(NX 手动拉伸却没问题)。
    # 修复前本组必红: 短线不剔除时闭链不复原。
    _ov = [DXLine((0, 0), (0, -3)),
           DXArc((5, 0), 5.0, math.pi / 2, math.pi),
           DXLine((0, 0), (0, -10)),
           DXLine((0, -10), (10, -10)),
           DXLine((10, -10), (10, 5)),
           DXLine((10, 5), (5, 5))]
    _ov_before, _ = find_chains(_ov)
    _ov_stubs = _stub_line_indices(_ov)
    _ov_after, _ = find_chains(
        [e for i, e in enumerate(_ov)
         if i not in {r[0] for r in _ov_stubs}])
    check("画过头短线: 剔除前闭链被拆开(复现整根不建模)",
          not _ov_before and [(r[0], r[1]) for r in _ov_stubs] == [(0, 2)]
          and abs(_ov_stubs[0][2] - 3.0) < 1e-9, str(_ov_stubs))
    check("画过头短线: 剔除后闭链恢复",
          len(_ov_after) == 1 and len(_ov_after[0]) == 5)
    _neg1 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 3)),
             DXLine((10, 3), (8, 3)), DXLine((8, 3), (0, 3)),
             DXLine((0, 3), (0, 0))]
    check("画过头短线: 两岔接点的正常短边不动",
          _stub_line_indices(_neg1) == [])
    _neg2 = _neg1 + [DXLine((0, 0), (0, -3))]
    check("画过头短线: 三岔接点但方向垂直的岔线不动",
          _stub_line_indices(_neg2) == [])
    _neg3 = _neg1 + [DXLine((0, 0), (3.0, 0.5))]
    check("画过头短线: 三岔接点但没压在同一条线上的短段不动",
          _stub_line_indices(_neg3) == [])
    _neg4 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 3)),
             DXLine((10, 3), (0, 3)), DXLine((0, 3), (0, 0)),
             DXLine((3, 0), (0, 0))]      # 反向描画的叠线也识别
    check("画过头短线: 反方向描画的叠线同样识别",
          [(r[0], r[1]) for r in _stub_line_indices(_neg4)] == [(4, 0)])

    check("_blend_ok: 丢体11%=正常(基准样板实证)",
          _blend_ok(41049.5, 36553.8))
    _good_rows = [(16, 3.9, 0), (19, 25.1, 0), (22, 0.0, 1),
                  (18, 0.0, 0)]
    _bad_rows = _good_rows + [(20, 0.0, 0), (23, 3.9, 0)]
    _sliver = _good_rows + [(22, 0.0, 2)]
    check("面体检: 好条全解析→通过", _faces_healthy(_good_rows)[0])
    check("面体检: 样条面不算异形(v1.24, 样条墙正常产物)",
          _faces_healthy(_bad_rows)[0])
    check("面体检: 零尺寸碎片→异形", not _faces_healthy(_sliver)[0]
          and "碎片" in _faces_healthy(_sliver)[1])
    check("_blend_ok: 丢体>25%=异形", not _blend_ok(100.0, 74.0))
    check("_blend_ok: 体积0=异形", not _blend_ok(100.0, 0.0))
    check("_blend_effective: 正常掉体11%→有效", _blend_effective(22080.7, 19648.8))
    check("_blend_effective: 空转掉0.007%→判无效(2026-09-17 实机)",
          not _blend_effective(19678.2, 19676.8))
    check("_blend_effective: 体积测不到不拦",
          _blend_effective(None, 90.0) and _blend_effective(100.0, None)
          and _blend_effective(0.0, 0.0))
    check("_blend_ok: 测不到不拦", _blend_ok(None, None))

    _rows = [(1, 10.0, 10.0, 3.9), (2, 10.0, 40.0, 3.9), (3, 50.0, 10.0, 3.9),
             (4, 10.0, 10.0, 300.0)]
    check("删面: 半径匹配+距离近→选中",
          _conn_face_pick(_rows, [(10.2, 10.0), (10.0, 39.8)], 3.9) == [1, 2])
    check("删面: 只有错半径面→放弃",
          _conn_face_pick([(1, 10.0, 10.0, 300.0)], [(10.0, 10.0)], 3.9) is None)
    check("删面: 距离超门控→放弃",
          _conn_face_pick([(1, 50.0, 50.0, 3.9)], [(10.0, 10.0)], 3.9) is None)

    # 出线口锚点按条封闭线辨认(v2.9 开放性判别, 2.dxf 链1 全 28 段固化):
    # 旧"最短两条线"选中槽底封口 3.6mm 对, 真出线口是间距 25mm 的 8mm 唇线对
    _c1 = [
        DXArc((3446.1933, 1434.4866), 19.0000, 2.8872, 4.2738),
        DXArc((3425.8107, 1391.0291), 29.0000, 6.2306, 7.4154),
        DXLine((3454.7707, 1389.5049), (3454.5837, 1385.9529)),
        DXArc((3425.6238, 1387.4771), 29.0000, 4.6271, 6.2306),
        DXArc((3421.5361, 1339.6515), 19.0000, 1.4855, 2.8872),
        DXLine((3403.1475, 1344.4325), (3380.5052, 1257.3467)),
        DXArc((3352.4383, 1264.6441), 29.0000, 2.8872, 6.0288),
        DXLine((3349.6999, 1369.3585), (3324.3715, 1271.9415)),
        DXArc((3338.0861, 1372.3781), 12.0000, 6.0288, 7.5996),
        DXLine((3341.1057, 1383.9920), (3343.1187, 1391.7346)),
        DXArc((3338.0861, 1372.3781), 20.0000, 6.0288, 7.5996),
        DXLine((3357.4425, 1367.3455), (3332.1141, 1269.9284)),
        DXArc((3352.4383, 1264.6441), 21.0000, 2.8872, 6.0288),
        DXLine((3395.4049, 1346.4456), (3372.7626, 1259.3598)),
        DXArc((3421.5361, 1339.6515), 27.0000, 1.4855, 2.8872),
        DXArc((3425.6238, 1387.4771), 21.0000, 4.6271, 6.2306),
        DXLine((3446.7817, 1389.9254), (3446.5948, 1386.3734)),
        DXArc((3425.8107, 1391.0291), 21.0000, 6.2306, 7.4154),
        DXArc((3446.1933, 1434.4866), 27.0000, 2.8872, 4.2738),
        DXLine((3437.7626, 1509.3598), (3420.0621, 1441.2807)),
        DXArc((3417.4383, 1514.6441), 21.0000, 6.0288, 9.1704),
        DXLine((3397.1141, 1519.9284), (3371.7856, 1422.5113)),
        DXArc((3352.4292, 1427.5440), 20.0000, 4.4580, 6.0288),
        DXLine((3349.4096, 1415.9302), (3347.3965, 1408.1876)),
        DXArc((3352.4292, 1427.5440), 12.0000, 4.4580, 6.0288),
        DXLine((3389.3715, 1521.9415), (3364.0431, 1424.5244)),
        DXArc((3417.4383, 1514.6441), 29.0000, 6.0288, 9.1704),
        DXLine((3445.5052, 1507.3467), (3427.8046, 1439.2676)),
    ]
    _k1 = [(i, False) for i in range(len(_c1))]
    _oms = _contour_outlet_mids(_k1, _c1)
    check("出线口锚点: 封闭线辨唇线弃槽底(2.dxf 链1 全轮廓)",
          len(_oms) == 2
          and abs(_oms[0][0] - 3342.1122) < 0.01
          and abs(_oms[0][1] - 1387.8633) < 0.01
          and abs(_oms[1][0] - 3348.403) < 0.01
          and abs(_oms[1][1] - 1412.0589) < 0.01, str(_oms))
    check("出线口锚点: 同图层混入跨口横线不误判",
          _contour_outlet_mids(
              _k1 + [(len(_c1), False)],
              _c1 + [DXLine((3356.8715, 1396.9415), (3345.2576, 1399.9611))])
          == _oms)
    check("出线口锚点: 同图层重复描画唇线不误判",
          _contour_outlet_mids(
              _k1 + [(len(_c1), False)],
              _c1 + [DXLine((3341.1057, 1383.992), (3343.1187, 1391.7346))])
          == _oms)
    check("出线口锚点: 同位重复线单元去重→放弃",
          _contour_outlet_mids(
              [(0, False), (1, False)],
              [DXLine((3341.1, 1384.0), (3343.1, 1391.7)),
               DXLine((3341.1, 1384.0), (3343.1, 1391.7))]) == [])
    check("出线口锚点: 全连线均在材料内→放弃(三角链)",
          _contour_outlet_mids(
              [(0, False), (1, False), (2, False)],
              [DXLine((0.0, 0.0), (10.0, 0.0)),
               DXLine((10.0, 0.0), (5.0, 8.0)),
               DXLine((5.0, 8.0), (0.0, 0.0))]) == [])
    # JRTFBX 标记图层(v2.10): 标记优先定位出线口, 两种画法兼容
    _fa = _fbx_anchor_points([DXLine((0.0, 0.0), (8.0, 0.0)),
                              DXLine((100.0, 0.0), (100.0, 30.0)),
                              DXArc((0.0, 0.0), 5.0, 0.0, 1.0)])
    check("JRTFBX: 短线取中点/长线取两端点/非线忽略",
          _fa == [(4.0, 0.0), (100.0, 0.0), (100.0, 30.0)], str(_fa))
    _fbx_boxes = [(0.0, 0.0, 20.0, 10.0), (100.0, 0.0, 120.0, 10.0)]
    _fp, _fw = _marker_mids_for_chains(_fbx_boxes,
                                       [(10.0, 5.0), (110.0, 5.0)], 10.0)
    check("JRTFBX: 标记就近分配两条链",
          _fp == [[(10.0, 5.0)], [(110.0, 5.0)]] and not _fw,
          str((_fp, _fw)))
    _fp2, _fw2 = _marker_mids_for_chains(_fbx_boxes, [(60.0, 60.0)], 10.0)
    check("JRTFBX: 离条超限的标记忽略并告警",
          _fp2 == [[], []] and len(_fw2) == 1 and "忽略" in _fw2[0],
          str((_fp2, _fw2)))
    _fa2 = _fbx_anchor_points([DXLine((0.0, 0.0), (8.0, 0.0)),
                               DXLine((0.0, 0.1), (8.0, 0.0))])
    check("JRTFBX: 同位重复标记去重(0.5mm, 防候选点翻倍)",
          _fa2 == [(4.0, 0.0)], str(_fa2))
    _mk_base = [DXLine((0.0, 0.0), (10.0, 0.0)), DXArc((0.0, 0.0), 5.0, 0.0, 1.0)]
    _mk_ents = [DXLine((0.0, 0.0), (10.0, 0.0)),
                DXArc((50.0, 0.0), 5.0, 0.0, 1.0),
                DXLine((0.0, 5.0), (8.0, 5.0))]
    _mk_add, _mk_dup, _mk_oth = _merge_marker_lines(_mk_base, _mk_ents)
    check("JRTFBX 并入: 下标用原始下标(重合丢弃/曲线不混淆)",
          _mk_add == [2] and _mk_dup == [0] and _mk_oth == [1],
          str((_mk_add, _mk_dup, _mk_oth)))
    check("方案二: 嵌入端未倒成→齐平端不倒圆",
          _flush_blend_allowed(False) is False
          and _flush_blend_allowed(None) is False)
    check("方案二: 嵌入端倒成→齐平端照常", _flush_blend_allowed(True) is True)
    with io.open(os.path.join(script_dir(), "cad3d", "modeling", "jrt.py"),
                 encoding="utf-8") as _jf:
        _jrt_src = _jf.read()
    check("jrt 删面愈合在位(_delete_faces_safe 定义+两端调用)",
          _jrt_src.count("_delete_faces_safe(") >= 3)
    check("jrt 出线口锚点按条封闭线(_contour_outlet_mids 已接入, CXK 路径已移除)",
          "_contour_outlet_mids(" in _jrt_src
          and 'layers.get("CXK")' not in _jrt_src)
    check("jrt JRTFBX 标记优先已接线(缺标记自动走推断)",
          'layers.get("JRTFBX")' in _jrt_src
          and "_marker_mids_for_chains(" in _jrt_src)
    check("jrt JRTFBX 封闭线并入轮廓闭链(实图与老图纸两种画法)",
          "nx_curves.setdefault(\"JRT\", []).append" in _jrt_src
          and 'layers.get("JRTFBX")' in _jrt_src)
    check("jrt JRTFBX 并入取原始实体下标(弧/圆混入不错位, v2.11 修复)",
          "_merge_marker_lines(" in _jrt_src
          and "_fbx_curves[_k]" in _jrt_src)
    check("jrt 标记重合丢弃数已记账(不再静默)",
          "跟 JRT 层的线完全重合" in _jrt_src)
    check("jrt 方案二已接线(_flush_blend_allowed+skip_flush)",
          "_flush_blend_allowed(" in _jrt_src and "skip_flush" in _jrt_src)
    check("jrt 画过头短线先剔除再接链(_stub_line_indices 已接线)",
          "_stub_rows = _stub_line_indices(" in _jrt_src
          and 'nx_curves["JRT"] = [' in _jrt_src)
    check("jrt 齐平端起试R按条高收小(_flush_start_r 已接线)",
          "_r_start = r_flush0" in _jrt_src
          and "r_flush0 = _flush_start_r(" in _jrt_src)
    # 端面圆角"降级重试"链路回归(2026-09-10): 用桩离线驱动 jrt._edge_blend_end_retry。
    # 判据: 异形/体积异常/NX 拒绝都要降 R 重试且每次撤销; 到下限仍不行则放弃并返回
    # 原 R; 齐平端(dome)才查型20 残留, 嵌入端不查。此前整条链路无任何测试覆盖。
    import types as _t_mod

    import cad3d.modeling.jrt as _mod_jrt
    _nx_keep = sys.modules.get("NXOpen")
    _nx_stub = _t_mod.ModuleType("NXOpen")
    _nx_stub.Session = _t_mod.ModuleType("_S")
    _nx_stub.Session.MarkVisibility = _t_mod.ModuleType("_MV")
    _nx_stub.Session.MarkVisibility.Invisible = 1
    sys.modules["NXOpen"] = _nx_stub

    class _RetrySession:
        def __init__(self):
            self.undos = 0

        def SetUndoMark(self, _vis, _name):
            return 1

        def UndoToMark(self, _mark, _name):
            self.undos += 1

    def _drive_retry(rows_at, vol_at, dome=False, raise_at=None,
                     noface_at=None):
        """按 R 分派桩行为跑一遍降级循环 → (返回, 试过的R序列, 会话, 日志)。"""
        tries, logs = [], []
        st = {"rows": [(1, 10.0, 1)], "v0": 100.0, "v1": 90.0, "after": False}
        sess = _RetrySession()
        _old = (_mod_jrt._body_volume, _mod_jrt._edge_blend_end,
                _mod_jrt._body_face_rows)

        def _vol(_wp, _b):
            # 一进一出计一次: 圆角前读到 v0, 圆角后读到 v1(与真实测量的调用
            # 次序同口径; 失败撤销后下一次再读回 v0)
            if st["after"]:
                st["after"] = False
                return st["v1"]
            return st["v0"]

        def _blend(_wp, _uf, _body, _z, r, _log, feat_name=None):
            k = round(float(r), 4)
            tries.append(k)
            if noface_at and k in noface_at:
                raise _mod_jrt._NoEndFace("高度 -47.5 处没有端面")
            if raise_at and k in raise_at:
                raise RuntimeError("NX 拒绝本次圆角")
            st["v0"], st["v1"] = vol_at.get(k, (100.0, 90.0))
            st["rows"] = rows_at.get(k, [(1, 10.0, 1)])
            st["after"] = True
            return object(), []

        _mod_jrt._body_volume = _vol
        _mod_jrt._edge_blend_end = _blend
        _mod_jrt._body_face_rows = lambda _uf, _b: st["rows"]
        try:
            got = _mod_jrt._edge_blend_end_retry(
                sess, None, None, object(), -47.5, 3.9, 3.7, 0.1,
                lambda m: logs.append(m), "CAD3D_TEST", "第 1 根上侧嵌入端",
                dome=dome)
        finally:
            (_mod_jrt._body_volume, _mod_jrt._edge_blend_end,
             _mod_jrt._body_face_rows) = _old
        return got, tries, sess, logs

    try:
        _R39_OK = [(1, 10.0, 1)]          # 平面, 零维 1 个 → 正常
        _R39_BAD = [(1, 10.0, 2)]         # 零维 2 个 → 碎片面(异形)
        _R39_SP20 = [(20, 0.0, 1)]        # 型20 样条面 → 齐平端判异形
        _g, _tr, _se, _lg = _drive_retry({}, {})
        check("圆角降级: 一次成就返回该 R, 不空跑不撤销",
              abs(_g[2] - 3.9) < 1e-9 and _tr == [3.9] and _se.undos == 0, str(_tr))
        _g, _tr, _se, _lg = _drive_retry({3.9: _R39_BAD, 3.8: _R39_OK}, {})
        check("圆角降级: 异形面 → 降 R 重试并撤销一次",
              abs(_g[2] - 3.8) < 1e-9 and _tr == [3.9, 3.8] and _se.undos == 1
              and "面不对" in "".join(_lg), str((_g[2], _tr, _se.undos)))
        _g, _tr, _se, _lg = _drive_retry(
            {3.9: _R39_BAD, 3.8: _R39_BAD, 3.7: _R39_BAD}, {})
        check("圆角降级: 到下限仍异形→放弃, 且每次撤销(不留半成品)",
              _g[0] is None and abs(_g[2] - 3.9) < 1e-9
              and _tr == [3.9, 3.8, 3.7] and _se.undos == 3,
              str((_g[0], _g[2], _tr, _se.undos)))
        _g, _tr, _se, _lg = _drive_retry({}, {3.9: (100.0, 50.0),
                                              3.8: (100.0, 90.0)})
        check("圆角降级: 体积异常(掉>25%) → 降 R 重试",
              abs(_g[2] - 3.8) < 1e-9 and _se.undos == 1
              and "体积不对" in "".join(_lg), str((_g[2], _lg)))
        _g, _tr, _se, _lg = _drive_retry({}, {}, raise_at={3.9, 3.8})
        check("圆角降级: NX 直接拒绝也降 R, 且失败那次留痕",
              abs(_g[2] - 3.7) < 1e-9 and _tr == [3.9, 3.8, 3.7]
              and _se.undos == 2 and "没做出来" in "".join(_lg),
              str((_g[2], _tr, _se.undos)))
        # 被 NX 裁成一条缝的空转圆角(体积几乎不变)必须降 R——此前只查"掉太多",
        # 会把这种假成功放行, 齐平端看起来"没做"(2026-09-17 实机)。
        _g, _tr, _se, _lg = _drive_retry({}, {3.9: (100.0, 99.99),
                                              3.8: (100.0, 90.0)})
        check("圆角降级: 空转(几乎没啃到料)→降 R 重试",
              abs(_g[2] - 3.8) < 1e-9 and _se.undos == 1
              and "没啃到料" in "".join(_lg), str((_g[2], _lg)))
        _g, _tr, _se, _lg = _drive_retry(
            {3.9: _R39_SP20, 3.8: _R39_SP20, 3.7: _R39_OK}, {}, dome=True)
        check("圆角降级: 齐平端(圆顶)判型20残留为异形 → 降 R",
              abs(_g[2] - 3.7) < 1e-9 and _se.undos == 2, str((_g[2], _tr)))
        _g, _tr, _se, _lg = _drive_retry({3.9: _R39_SP20}, {}, dome=False)
        check("圆角降级: 嵌入端不查型20(同样残留直接放行)",
              abs(_g[2] - 3.9) < 1e-9 and _tr == [3.9], str((_g[2], _tr)))
        _g, _tr, _se, _lg = _drive_retry({}, {}, noface_at={3.9, 3.8, 3.7})
        check("圆角降级: 找不到端面→立刻放弃, 不空降 3 次",
              _g[0] is None and _tr == [3.9] and _se.undos == 0
              and "没有端面" in "".join(_lg), str((_tr, _se.undos, _lg)))
        _g, _tr, _se, _lg = _drive_retry(
            {3.9: _R39_BAD, 3.8: _R39_BAD, 3.7: _R39_BAD}, {})
        check("圆角降级: 到下限留一行总账(不是静默返回)",
              "一路试到下限" in "".join(_lg), str(_lg))
    finally:
        if _nx_keep is None:
            sys.modules.pop("NXOpen", None)
        else:
            sys.modules["NXOpen"] = _nx_keep
    check("护栏: 全图层但半径收窄→放行(压线板式需求)",
          not anchors_overflow(list(range(47)),
                               sanitize_std_rule({"layer": "", "r_max": 20})))

    cfg = _USER_CFG
    check("BOOL_OPTS 无停用项", all(b[0] != "OFF" for b in BOOL_OPTS))
    if cfg is None:
        check("ZMODE 无绝对Z项/配置缺失回退内置",
              all(z[0] != "ABS" for z in ZMODE_OPTS)
              and [z[0] for z in ZMODE_OPTS]
              == [d[0] for d in _ZMODE_FALLBACK])
    else:
        check("ZMODE 无绝对Z项/由config表驱动(v1.32)",
              all(z[0] != "ABS" for z in ZMODE_OPTS)
              and [z[0] for z in ZMODE_OPTS] ==
              [d[0] for d in cfg.ZMODE_DEFS]
              and [z[1] for z in ZMODE_OPTS] ==
              [d[1] + "+偏移" for d in cfg.ZMODE_DEFS])
    check("_std_z 查表: CX_TOP 仍正确(CX -30~-65 → -30)",
          _std_z({"CX": (-30.0, -65.0)},
                 sanitize_std_rule({"z_mode": "CX_TOP"})) == -30.0)
    _ZMODE_DEFS.append(("JT_BOTTOM", "JT底面", "JT", "BOTTOM"))
    try:
        _ok_new = _std_z({"FLB": (-40.0, -90.0), "JT": (-30.0, -100.0)},
                         sanitize_std_rule({"z_mode": "JT_BOTTOM"}))
    finally:
        _ZMODE_DEFS.pop()
    check("_std_z 查表: 动态加基准(JT底→-100)即加即用", _ok_new == -100.0)
    check("_rule_usable: 无ref不可用且支持整型与浮点坐标",
          not _rule_usable({"ref": None})
          and not _rule_usable({"ref": [1, 2]})
          and _rule_usable({"ref": [1.0, 2.0, 3.0]})
          and _rule_usable({"ref": [0, 0, 0]}))
    check("_unusable_names: 列出未配置件",
          _unusable_names({"a.prt": {"ref": [0.0, 0.0, 0.0]},
                           "b.prt": {"ref": None}}) == ["b.prt"])
    _two = [("大水口-25.prt", {"layer": "RZ", "z_mode": "FLB_BOTTOM",
                               "ref": [1.0, 2.0, 3.0]}),
            ("大水口", {"layer": "RZ", "z_mode": "FLB_BOTTOM"})]
    _hit = std_part_defaults("大水口-25.prt", table=_two)
    check("两级匹配: 精确行命中",
          _hit is not None and _hit.get("ref") == [1.0, 2.0, 3.0])
    _hit2 = std_part_defaults("大水口-18.prt", table=_two)
    check("两级匹配: 落关键词行(无ref)",
          _hit2 is not None and _hit2.get("ref") is None)
    # 垫片兜底(2026-09-18 定案): 图纸没有 DK 层 → layer=DK 的件本次临时改走热咀的
    # 定位层与半径; Z 基准/布尔方式仍用件自己的; 有 DK 或没选 DK 件时一律不动。
    _dk_rules = {"垫片.prt": {"layer": "DK", "r_min": 0.0, "r_max": 5.0,
                            "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT",
                            "ref": [0.0, 0.0, 0.0]},
                 "大水口-25.prt": {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                                 "z_mode": "FLB_BOTTOM", "ref": [0.0, 0.0, 0.0]}}
    _dk_fb = dk_fallback_rules(_dk_rules, has_dk=False)
    _nz_def = std_part_defaults("热咀")
    check("DK 定位件判定: 只认 layer=DK(大小写无关), 坏输入安全",
          dk_located_names(_dk_rules) == ["垫片.prt"]
          and dk_located_names({"a.prt": {"layer": "dk"}}) == ["a.prt"]
          and dk_located_names(None) == []
          and dk_located_names({"x": None}) == []
          and dk_located_names({"y": 3}) == [],
          str(dk_located_names(_dk_rules)))
    check("DK兜底: 没DK层时只有DK件入选",
          list(_dk_fb) == ["垫片.prt"],
          str(list(_dk_fb)))
    check("DK兜底: 定位层与半径换成热咀那套",
          _nz_def is not None
          and _dk_fb["垫片.prt"]["layer"] == _nz_def["layer"]
          and _dk_fb["垫片.prt"]["r_min"] == _nz_def["r_min"]
          and _dk_fb["垫片.prt"]["r_max"] == _nz_def["r_max"],
          "%r vs %r" % (_dk_fb.get("垫片.prt"), _nz_def))
    check("DK兜底: Z基准与布尔方式仍用件自己的",
          _dk_fb["垫片.prt"]["z_mode"] == "FLB_TOP"
          and _dk_fb["垫片.prt"]["bool_mode"] == "PLACE_SUBTRACT")
    check("DK兜底: 有DK层时一律不动",
          dk_fallback_rules(_dk_rules, has_dk=True) == {})
    check("DK兜底: 没选DK件→空",
          dk_fallback_rules({"a.prt": {"layer": "RZ"}}, False) == {})
    check("DK兜底: 坏输入安全",
          dk_fallback_rules(None, False) == {}
          and dk_fallback_rules({"x": None}, False) == {}
          and dk_fallback_rules({"x": 3}, False) == {})
    check("DK兜底: 不改传入的原表(记忆靠它还原)",
          _dk_rules["垫片.prt"]["layer"] == "DK"
          and _dk_rules["垫片.prt"]["r_max"] == 5.0)
    _old = sanitize_std_rule({"bool_mode": "OFF", "z_mode": "ABS"})
    check("sanitize: 旧OFF/ABS回默认",
          _old["bool_mode"] == "PLACE" and _old["z_mode"] == "FLB_TOP")
    check("护栏常量来自配置",
          cfg is None or STD_MAX_ANCHORS == cfg.STD_MAX_ANCHORS)

    jm1 = jrt_with_memory({"schema": SCHEMA_VERSION,
                           "jrt_se": [-38.0, -45.5]},
                          {"FLB": (-40.0, -90.0)})
    check("jrt_with_memory 有记忆用记忆",
          jm1["start"] == -38.0 and jm1["end"] == -45.5
          and jm1["blend_r"] == 3.9 and jm1["r_step"] == 0.1
          and jm1["r_min"] == 3.7)
    jm2 = jrt_with_memory({"schema": SCHEMA_VERSION},
                          {"FLB": (-40.0, -90.0)})
    check("jrt_with_memory 无记忆随FLB联动",
          jm2["start"] == -40.0 and jm2["end"] == -47.5)
    check("save_state 支持 jrt_se 字段",
          "jrt_se" in _insp.signature(save_state).parameters)
    check("save_state 支持 jt_link_mode 字段",
          "jt_link_mode" in _insp.signature(save_state).parameters)
    check("替换两页去记忆(v3.1): 不再有映射存取",
          "std_replace_map" not in _insp.signature(save_state).parameters
          and not hasattr(_mod_state, "save_replace_map"))

    _ring = [DXLine((483.5, 84.9), (483.5, 91.0)),
             DXLine((483.5, 91.0), (491.5, 91.0)),
             DXLine((491.5, 91.0), (491.5, 84.9)),
             DXArc((500.0, 84.9), 8.5, 0, math.pi),
             DXLine((508.5, 84.9), (508.5, 91.0)),
             DXLine((516.5, 91.0), (508.5, 91.0)),
             DXLine((516.5, 91.0), (516.5, 84.9)),
             DXArc((500.0, 84.9), 16.5, math.pi, 0)]
    _ring_ch = [(i, False) for i in range(len(_ring))]
    _rc = _chain_connectors(_ring_ch, _ring)
    check("连接线泛化: 环形通道4条跨接线",
          len(_rc) == 4, str(_rc))
    _om = _chain_outlet_mids(_ring_ch, _ring)
    check("出线口线中点: 2条口线(期刊删除面锚点)",
          len(_om) == 2
          and any(abs(m[0] - 487.5) < 0.01 for m in _om)
          and any(abs(m[0] - 512.5) < 0.01 for m in _om), str(_om))

    check("sanitize ref: 合法3数保留",
          sanitize_std_rule({"ref": [1, 2.5, -3]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 数字字符串转float",
          sanitize_std_rule({"ref": ["1", "2.5", "-3"]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 非3长/坏值/缺失→None",
          sanitize_std_rule({"ref": [1, 2]})["ref"] is None
          and sanitize_std_rule({"ref": [1, "x", 3]})["ref"] is None
          and sanitize_std_rule({})["ref"] is None)

    _disc2 = _mod_std_rules.discover_std_parts
    _mod_std_rules.discover_std_parts = lambda: ["垫片.prt"]
    globals()["discover_std_parts"] = _mod_std_rules.discover_std_parts
    try:
        _mr = merge_std_rules({"schema": SCHEMA_VERSION,
                               "std_parts": {"垫片.prt": {
                                   "layer": "DK", "ref": [7, 8, 9]}}})
    finally:
        _mod_std_rules.discover_std_parts = _disc2
        globals()["discover_std_parts"] = _disc2
    check("记忆往返: ref 不丢",
          _mr["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])
    _rt = json.loads(json.dumps(_mr))
    _mr2 = merge_std_rules({"schema": SCHEMA_VERSION, "std_parts": _rt})
    check("json 往返: ref 不丢", _mr2["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])

    check("齐平端起试R: 7.5厚条→3.7(用户手工值)",
          _flush_start_r(3.9, 3.7, 7.5) == 3.7)
    check("齐平端起试R: 厚条→用满blend_r",
          _flush_start_r(3.9, 3.7, 20.0) == 3.9)
    check("齐平端起试R: 不低于r_min",
          _flush_start_r(3.9, 3.7, 4.0) == 3.7)
    _nohit = std_part_defaults("未知新件XYZ.prt")
    check("表外新件→None(恢复=通用安全默认)",
          _nohit is None
          and sanitize_std_rule(_nohit)["layer"] == ""
          and sanitize_std_rule(_nohit)["bool_mode"] == "PLACE")
    sr = sanitize_std_rule({"off_x": "abc", "layer": "rz", "z_mode": "XX"})
    check("规则规范化: 坏偏移回0/坏z_mode回默认",
          sr["off_x"] == 0.0 and sr["layer"] == "RZ"
          and sr["z_mode"] == "FLB_TOP")
    check("规则规范化: CXK/CX_TOP 合法保留",
          sanitize_std_rule({"layer": "cxk", "z_mode": "cx_top",
                              "off_x": 5})["layer"] == "CXK")

    check("外部配置已加载(nx_std_config.py)", cfg is not None,
          "缺失时走内置兜底表")
    for k, v in (cfg.STD_PART_DEFAULTS if cfg is not None else []):
        rr = sanitize_std_rule(v)
        check("配置表条目合法: %s" % k,
              rr["layer"] in LAYER_CODES + list(LINE_ANCHOR_LAYERS) + [""]
              and rr["z_mode"] in [z for z, _t in ZMODE_OPTS]
              and rr["bool_mode"] in [b for b, _t in BOOL_OPTS]
              and rr["dir"] in [dd for dd, _t in DIR_OPTS])
    check("JRT 三参来自配置",
          cfg is None or (DEFAULT_JRT["blend_r"] == cfg.JRT_BLEND_R_DEFAULT
                          and DEFAULT_JRT["r_min"] == cfg.JRT_R_MIN_DEFAULT))
    check("配置表无重复关键词(后者永不生效)",
          cfg is None or len([k for k, _v in cfg.STD_PART_DEFAULTS])
          == len(set(k for k, _v in cfg.STD_PART_DEFAULTS)))

    _disc = _mod_std_rules.discover_std_parts
    _mod_std_rules.discover_std_parts = lambda: ["垫片.prt"]
    globals()["discover_std_parts"] = _mod_std_rules.discover_std_parts
    try:
        m_stale = merge_std_rules({"schema": SCHEMA_VERSION - 1,
                                   "std_parts": {"垫片.prt": {"layer": "LS"}}})
        m_ok = merge_std_rules({"schema": SCHEMA_VERSION,
                                "std_parts": {"垫片.prt": {"layer": "LS"}}})
    finally:
        _mod_std_rules.discover_std_parts = _disc
        globals()["discover_std_parts"] = _disc
    check("JSON 记忆 schema 守卫",
          m_stale["垫片.prt"]["layer"] == "DK"
          and m_ok["垫片.prt"]["layer"] == "LS")

    sxml = build_selection_dlx(["a.prt", "b.prt"], ["b.prt"])
    try:
        ET.fromstring(sxml)
        check("选择对话框 dlx 良构", True)
    except ET.ParseError as ex:
        check("选择对话框 dlx 良构", False, str(ex))
    check("选择对话框 toggle=2 且 b 选中",
          sxml.count('class="UICOMP_toggle" hierarchy="UGS::UICOMP_group"') == 2
          and 'id="SEL1"' in sxml)

    # 3Dtest.dxf 实际在 test/fixtures/ 下: 此前指向仓库根目录, isfile 恒 False,
    # 这组真图链回归断言从未执行过也无提示(死代码)
    real2 = os.path.join(script_dir(), "test", "fixtures", "3Dtest.dxf")
    if os.path.isfile(real2):
        layers_r2, _ = parse_dxf(real2)
        jrt_ents = layers_r2.get("JRT") or []
        closed_r, _o = find_chains(jrt_ents)
        if len(closed_r) == 2:
            c1 = _chain_connectors(closed_r[0], jrt_ents)
            c2 = _chain_connectors(closed_r[1], jrt_ents)
            ok1 = (len(c1) == 2
                   and abs(c1[0][0] - 4615.7) < 1.5 and abs(c1[0][1] - 1366.3) < 1.5
                   and abs(c1[1][0] - 4616.2) < 1.5 and abs(c1[1][1] - 1391.3) < 1.5)
            ok2 = (len(c2) == 2
                   and abs(min(c2[0][0], c2[1][0]) - 4342.1) < 1.5
                   and abs(max(c2[0][0], c2[1][0]) - 4348.4) < 1.5)
            check("3Dtest 链1 连接线≈(4615.7,1366.3)/(4616.2,1391.3)", ok1, str(c1))
            check("3Dtest 链2 连接线≈(4342.1,1387.9)/(4348.4,1412.1)", ok2, str(c2))
    else:
        check("3Dtest 真图链回归可用", False, "fixture 缺失: %s" % real2)
    _dp = layers.get("DP") or []
    profs_dpx, opens_dp, _ = organize_loops(_dp)
    check("DP 垫片嵌套", _dp and len(profs_dpx) == 1 and len(profs_dpx[0]["holes"]) == 1,
          "DP 层缺失或解析回归" if not _dp else "")
    _flb = layers.get("FLB") or []
    profs_flb, _o, _c = organize_loops(_flb)
    check("FLB 双通道=2 轮廓", len(profs_flb) == 2)

    xml = build_dlx(default_params())
    try:
        ET.fromstring(xml)
        check("dlx XML 良构", True)
    except ET.ParseError as ex:
        check("dlx XML 良构", False, str(ex))
    dbl = xml.count('<item Expanded="1" class="UICOMP_double"')
    check("dlx double 块数=19(图层14+JRT5)", dbl == 19, "got %d" % dbl)

    r = sanitize_std_rule({"layer": "rz", "r_min": "abc", "r_max": 5, "bool_mode": "XX"})
    check("规则规范化", r["layer"] == "RZ" and r["r_min"] == 0.0
          and r["bool_mode"] == "PLACE")
    r2 = sanitize_std_rule({"r_min": 10, "r_max": 2})
    check("半径区间自动交换", r2["r_min"] == 2.0 and r2["r_max"] == 10.0)
    check("文件名猜规则", guess_std_rule("热咀big.prt")["layer"] == "RZ"
          and guess_std_rule("screw_M8.prt")["layer"] == "LS")

    lay_c = {"RZ": [DXCircle((100, 20), 11.35), DXCircle((100, 100), 11.35),
                    DXArc((100, 20), 11.35, 0, math.pi)],
             "LS": [DXCircle((10, 10), 4.25)]}
    a1 = collect_circle_anchors(lay_c, sanitize_std_rule(
        {"layer": "RZ", "r_min": 10, "r_max": 12}))
    check("圆心锚点筛选+同心去重", len(a1) == 2, str(a1))
    a2 = collect_circle_anchors(lay_c, sanitize_std_rule({"layer": ""}))
    check("全图层锚点", len(a2) == 3, "got %d" % len(a2))
    check("_std_z 负区间", _std_z({"FLB": (-40, -85)},
                                  sanitize_std_rule({"z_mode": "FLB_TOP",
                                                     "off_z": -5})) == -45.0
          and _std_z({"FLB": (-40, -85)},
                     sanitize_std_rule({"z_mode": "FLB_BOTTOM"})) == -85.0)

    xml2 = build_dlx(default_params(), dict(DEFAULT_JRT))
    check("窗口②无标准件组(v1.35 休眠段删除)",
          'id="grp_std"' not in xml2 and "SP0_" not in xml2
          and 'id="jrt_start"' in xml2)
    gi = _group_item("g1", "标题", _blk_label("l1", "x"), columns=2, collapsed=True)
    check("组可收起(collapsed)", 'id="Expanded" mask="0" name="Expanded" sname="Expanded" '
          'source="2" type="logical" value="False"' in gi)
    fake_rules = {"a.prt": sanitize_std_rule({"layer": "DK"}),
                  "b.prt": sanitize_std_rule({"layer": "LS"})}
    sxml = build_std_dlx(fake_rules, default_params())
    try:
        ET.fromstring(sxml)
        check("标准件参数窗口 dlx 良构", True)
    except ET.ParseError as ex:
        check("标准件参数窗口 dlx 良构", False, str(ex))
    _sxml_cxk = build_std_dlx(
        {"接线盒-24针.prt": sanitize_std_rule({"layer": "CXK",
                                                "z_mode": "CX_TOP"}),
         "垫片.prt": sanitize_std_rule({"layer": "DK"})},
        default_params())
    check("CXK件无半径框/圆心件有(v1.31)",
          "接线盒" in _sxml_cxk
          and 'value="SP0_rmin"' in _sxml_cxk
          and 'value="SP0_rmax"' in _sxml_cxk
          and 'value="SP1_rmin"' not in _sxml_cxk
          and 'value="SP1_rmax"' not in _sxml_cxk)
    check("标准件参数窗口 2 组+Z标签",
          sxml.count('id="grp_SP') == 2 and 'id="SP0_zval"' in sxml)
    check("标准件参数窗口组默认展开(v1.16)",
          'name="Expanded" sname="Expanded" '
          'source="2" type="logical" value="False"' not in sxml)
    check("全件含重置按钮(v1.19, 含无默认件)",
          'id="SP0_reset"' in sxml and 'id="SP1_reset"' in sxml)
    sxml_w = build_std_dlx({"垫片.prt": sanitize_std_rule({})}, default_params())
    check("有默认件含重置按钮(垫片)", 'id="SP0_reset"' in sxml_w
          and 'id="SP0_zval"' in sxml_w)
    g6 = guess_std_rule("点胶口-25.prt")
    check("猜测: 点胶口→RZ/FLB底(与大水口同逻辑)",
          g6["layer"] == "RZ" and g6["z_mode"] == "FLB_BOTTOM")

    # 11b. v1.35 审计修复回归断言
    _td = _tf.mkdtemp(prefix="cad3d_selftest_")
    try:
        _empty = os.path.join(_td, "empty.dxf")
        with io.open(_empty, "w", encoding="ascii", newline="\n") as _f:
            _f.write("0\nEOF\n")
        _el, _es = parse_dxf(_empty)
        check("空 DXF 不崩(无 ENTITIES 段)", _el == {} and _es["total"] == 0)
        _uns_dxf = os.path.join(_td, "uns.dxf")
        with io.open(_uns_dxf, "w", encoding="ascii", newline="\n") as _f:
            _f.write("\n".join(
                ["0", "SECTION", "2", "ENTITIES",
                 "0", "LWPOLYLINE", "8", "FLB", "90", "3", "70", "0",
                 "10", "0", "20", "0", "10", "10", "20", "0",
                 "10", "10", "20", "10",
                 "0", "LINE", "8", "FLB",
                 "10", "0", "20", "0", "11", "10", "21", "0",
                 "0", "LWPOLYLINE", "8", "JRT", "90", "2", "70", "1",
                 "10", "0", "20", "200", "10", "5", "20", "200",
                 "0", "ENDSEC", "0", "EOF"]))
        _ul, _us = parse_dxf(_uns_dxf)
        check("不支持实体计数(LWPOLYLINE 不静默丢)",
              _us["unsupported"].get("LWPOLYLINE") == 2
              and _us["unsupported_model"] == 1
              and _us["total"] == 1 and len(_ul.get("FLB") or []) == 1,
              str(_us))
        # 2026-09-12 全面审查修复回归(解析器/拓扑/日志)
        _sl_dxf = os.path.join(_td, "slope.dxf")
        _sl_rows = ["0", "SECTION", "2", "ENTITIES",
                    "0", "LINE", "8", "FLB",
                    "10", "0", "20", "0", "30", "0",
                    "11", "10", "21", "0", "31", "10",
                    "0", "ENDSEC", "0", "EOF"]
        with io.open(_sl_dxf, "w", encoding="ascii", newline="\n") as _f:
            _f.write("\n".join(_sl_rows))
        _sl, _ss = parse_dxf(_sl_dxf)
        check("斜线终点 Z(组码31)计入非平面(不静默压平)",
              _ss["nonplanar"] == 1 and _ss["total"] == 1, str(_ss))
        _zl_dxf = os.path.join(_td, "zerolen.dxf")
        _zl_rows = ["0", "SECTION", "2", "ENTITIES",
                    "0", "LINE", "8", "FLB",
                    "10", "5", "20", "5", "11", "5", "21", "5",
                    "0", "ENDSEC", "0", "EOF"]
        with io.open(_zl_dxf, "w", encoding="ascii", newline="\n") as _f:
            _f.write("\n".join(_zl_rows))
        _zl, _zs = parse_dxf(_zl_dxf)
        check("零长线丢弃后 total 不虚增", _zs["total"] == 0 and _zl == {})
        _da_dxf = os.path.join(_td, "degen.dxf")
        _da_rows = ["0", "SECTION", "2", "ENTITIES",
                    "0", "ARC", "8", "FLB",
                    "10", "0", "20", "0", "40", "10",
                    "50", "30", "51", "30",
                    "0", "ENDSEC", "0", "EOF"]
        with io.open(_da_dxf, "w", encoding="ascii", newline="\n") as _f:
            _f.write("\n".join(_da_rows))
        _da, _ds = parse_dxf(_da_dxf)
        check("退化弧(起终角相同)丢弃不拉成整圆", _da == {} and _ds["total"] == 0)
        # 两段围成闭合回路: 输入组序 [seg1, seg0], seg0 需翻转才能接上
        _mg = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (0, 0))]
        _ord = _reorder_group_chains([[(1, False)], [(0, True)]], _mg)
        _oh, _ot = (_chain_head_tail(_ord, _mg) if _ord is not None
                    else (None, None))
        check("多链并组按端点连通性重排成链序(含整链翻转)",
              _ord is not None and [i for i, _r in _ord] == [1, 0]
              and _oh is not None and _ot is not None
              and abs(_oh[0] - _ot[0]) < 1e-6 and abs(_oh[1] - _ot[1]) < 1e-6)
        check("_fmt_num: -0.0 归一为 0", _fmt_num(-0.0) == "0")
        _gl = [DXLine((0, 0), (10.0, 0.0)), DXLine((9.994, 0.0), (20.0, 0.0))]
        _gc, _go = find_chains(_gl)
        check("格点边界断口仍能连链(邻桶)",
              not _gc and len(_go) == 1 and len(_go[0]) == 2)
        _tj = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (20, 0)),
               DXLine((10, 0), (10, 10))]
        _tc, _to = find_chains(_tj)
        check("T形三叉: 直线延续优先(不串错链)",
              not _tc and len(_to) == 2 and {i for i, _r in _to[0]} == {0, 1})
        _dp, _do, _ = organize_loops(_sq(0, 0, 100, 100) + _sq(0, 0, 100, 100))
        check("重复描线环去重(不被误判为孔)",
              len(_dp) == 1 and not _dp[0]["holes"], "profiles=%d" % len(_dp))
        check("-Z 放置位移(ref 随姿态旋转)",
              _place_delta((10.0, 2.0, 3.0), False, (1.0, 1.0, 1.0))
              == (-9.0, -1.0, -2.0)
              and _place_delta((10.0, 2.0, 3.0), True, (1.0, 1.0, 1.0))
              == (-9.0, 3.0, 4.0))
        check("merge_params 坏类型不崩",
              merge_params({"schema": SCHEMA_VERSION, "params": [1, 2]})
              == default_params()
              and merge_params({"schema": SCHEMA_VERSION, "params": "x"})
              == default_params()
              and merge_params(None) == default_params())
        _mp = merge_params({"schema": SCHEMA_VERSION,
                            "params": {"FLB": ["1.5", 2], "CX": (3, 4),
                                       "BAD": (1, 2)}})
        check("merge_params 合法值照收",
              _mp["FLB"] == (1.5, 2.0) and _mp["CX"] == (3.0, 4.0))
        check("schema 不符→params 一并回默认(文档口径)",
              merge_params({"schema": SCHEMA_VERSION - 1,
                            "params": {"FLB": (1.0, 2.0)}}) == default_params())
        check("selected 坏类型容错",
              _name_list(None) == [] and _name_list(5) == []
              and _name_list("ab") == []
              and _name_list(["a", 2]) == ["a", "2"])
        check("config 标量非法回默认不崩",
              _cfg_num("abc", 7.5) == 7.5 and _cfg_num(float("nan"), 3.0) == 3.0
              and _cfg_num("3.5", 1.0) == 3.5
              and _cfg_int(object(), 70) == 70
              and _cfg_int(float("inf"), 70) == 70)

        # 坏 JSON 记忆隔离留证
        _bad = os.path.join(_td, "nx_extrude_params.json")
        with io.open(_bad, "w", encoding="utf-8") as _f:
            _f.write("{oops not json")
        _saved_jp = _mod_state._json_path
        _mod_state._json_path = lambda: _bad
        globals()["_json_path"] = lambda: _bad
        _ok_iso = _ok_atomic = False
        try:
            _st = load_state()
            _ok_iso = (isinstance(_st, dict) and not _st and
                       [n for n in os.listdir(_td)
                        if n.startswith("nx_extrude_params.json.bad-")] != [])
        finally:
            _mod_state._json_path = _saved_jp
            globals()["_json_path"] = _saved_jp
        check("坏 JSON 记忆隔离留证(.bad-*)", _ok_iso)

        _mod_state._json_path = lambda: _bad
        globals()["_json_path"] = lambda: _bad
        try:
            save_state("X:/a.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2))
            _st2 = load_state()
            _ok_atomic = (_st2.get("dxf_path") == "X:/a.dxf"
                          and _st2.get("selected") == ["a.prt"]
                          and not [n for n in os.listdir(_td)
                                   if n.endswith(".tmp")])
        finally:
            _mod_state._json_path = _saved_jp
            globals()["_json_path"] = _saved_jp
        check("save_state 原子写+类型容错", _ok_atomic)

        _jp3 = os.path.join(_td, "jt_mem_test.json")
        if os.path.isfile(_jp3):
            os.remove(_jp3)
        _mod_state._json_path = lambda: _jp3
        globals()["_json_path"] = lambda: _jp3
        try:
            save_state("X:/a.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2),
                       jt_link_mode="针阀模式")
            save_state("X:/b.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2))
            _st3 = load_state()
        finally:
            _mod_state._json_path = _saved_jp
            globals()["_json_path"] = _saved_jp
        check("jt_link_mode 传 None 保留旧值(v1.38)",
              _st3.get("jt_link_mode") == "针阀模式"
              and _st3.get("dxf_path") == "X:/b.dxf")
        try:
            os.remove(_jp3)
        except OSError:
            pass

        class _FakeTop(object):
            def __init__(self):
                self.calls = 0

            def FindBlock(self, _bid):
                self.calls += 1
                return None

        class _FakeDialog(object):
            def __init__(self):
                self.TopBlock = _FakeTop()

        class _FakeBase(_BlockDialogBase):
            def __init__(self):
                self.blocks = {}
                self.theDialog = _FakeDialog()

        _fb = _FakeBase()
        _fb._find("x")
        _fb._find("x")
        check("_find None 不缓存(可重试)", _fb.theDialog.TopBlock.calls == 2)

        _big = {"RZ": [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                       for i in range(2000)]
                + [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                   for i in range(2000)]}
        _t0 = time.time()
        _ab = collect_circle_anchors(_big, sanitize_std_rule({"layer": "RZ"}))
        _dt = time.time() - _t0
        check("锚点去重 4000 实体 <2s 且去重正确",
              len(_ab) == 2000 and _dt < 2.0, "%.3fs" % _dt)

        _many = []
        for _r in range(200):
            _mx = float((_r % 20) * 30)
            _my = float((_r // 20) * 30)
            _many += _sq(_mx, _my, 20, 20)
        _t0 = time.time()
        _mp2, _mo2, _ = organize_loops(_many)
        _dt2 = time.time() - _t0
        check("organize_loops 200 环冒烟 <3s",
              len(_mp2) == 200 and _dt2 < 3.0, "%.3fs" % _dt2)

        # 11. 边界条件与异常容错断言(v1.40 审计回归)
        check("_bbox 空序列返回全零不崩溃", _bbox([]) == (0.0, 0.0, 0.0, 0.0))
        _r_none = resolve_dxf_path(None)
        _r_bad = resolve_dxf_path(123)
        check("resolve_dxf_path 传 None/坏类型容错",
              isinstance(_r_none, str) and isinstance(_r_bad, str) and _r_none == _r_bad)
        check("jt_mode_with_memory 传 None 容错",
              jt_mode_with_memory(None) == JT_LINK_DEFAULT)
        _jrt_none = jrt_with_memory(None, None)
        check("jrt_with_memory 传 None 容错且结构完整",
              isinstance(_jrt_none, dict) and "blend_r" in _jrt_none)
        check("collect_circle_anchors 空规则不抛 KeyError",
              collect_circle_anchors({}, {}) == [])
        _tdlx = _temp_dlx_path("cad3d_test")
        check("_temp_dlx_path 返回合法 dlx 路径",
              isinstance(_tdlx, str) and _tdlx.endswith(".dlx"))

        # 退化零/负半径圆弧在解析期自动过滤验证
        _deg_dxf = os.path.join(_td, "deg.dxf")
        with io.open(_deg_dxf, "w", encoding="ascii") as _f_deg:
            _f_deg.write("0\nSECTION\n2\nENTITIES\n"
                         "0\nCIRCLE\n8\nFLB\n10\n0\n20\n0\n30\n0\n40\n0.0\n"
                         "0\nARC\n8\nFLB\n10\n0\n20\n0\n30\n0\n40\n-1.0\n50\n0\n51\n90\n"
                         "0\nCIRCLE\n8\nFLB\n10\n10\n20\n10\n30\n0\n40\n5.0\n"
                         "0\nENDSEC\n0\nEOF\n")
        _deg_layers, _deg_stats = parse_dxf(_deg_dxf)
        check("零/负半径圆弧在解析期自动过滤",
              len(_deg_layers.get("FLB", [])) == 1 and _deg_layers["FLB"][0].r == 5.0)

        # 跨模块调用容错断言(互调安全)
        check("_std_z 传 None/空字典安全回退",
              isinstance(_std_z(None, None), float) and isinstance(_std_z({}, {}), float))
        check("_place_delta 传 None/残缺列表不越界",
              _place_delta(None, False, None) == (0.0, 0.0, 0.0)
              and _place_delta([1.0], True, []) == (-1.0, 0.0, 0.0))
        check("build_std_dlx 空/残缺规则生成良构 XML",
              "Dialog" in build_std_dlx({"part.prt": {}}, {}))
        _bld_b, _bld_r = build_layer(None, None, "FLB", "分流板", "target", {}, {}, None, [], Log(), {})
        check("build_layer 传 None 参数安全跳过不崩溃", _bld_b == [] and _bld_r == [])

        # 12. AutoCAD DWG 后台转换与自动销毁验证
        from cad3d.geom.dwg_converter import (
            find_acad_executable, convert_dwg_to_dxf, DwgConversionError
        )
        _acad_exe, _is_core = find_acad_executable()
        check("AutoCAD 转换程序智能探测(返回元组)",
              (_acad_exe is None or isinstance(_acad_exe, str)) and isinstance(_is_core, bool))

        _fixture_dwg = os.path.join(script_dir(), "test", "fixtures", "3Dtest.dwg")
        if _acad_exe and os.path.isfile(_fixture_dwg):
            _conv_logs = []
            _conv_dxf = convert_dwg_to_dxf(_fixture_dwg, log=_conv_logs.append)
            check("DWG 后台自动转 DXF 生成有效文件",
                  os.path.isfile(_conv_dxf) and os.path.getsize(_conv_dxf) > 1000)
            _dwg_layers, _dwg_stats = parse_dxf(_conv_dxf)
            check("DWG 转换产物 DXF 可被核心解析器完整解析",
                  "FLB" in _dwg_layers and _dwg_stats["total"] > 50)
            # v2.4 提速: 同图二次转换应命中缓存(不再起 AutoCAD, 秒回同一路径)
            _hit_logs = []
            _hit_t0 = time.time()
            _conv_hit = convert_dwg_to_dxf(_fixture_dwg, log=_hit_logs.append)
            _hit_dt = time.time() - _hit_t0
            check("DWG 转换缓存二次命中(免起 AutoCAD 复用)",
                  _conv_hit == _conv_dxf
                  and any("图纸没改过" in m for m in _hit_logs),
                  "耗时 %.3fs" % _hit_dt)
            try:
                os.remove(_conv_dxf)
            except Exception:
                pass
            check("DWG 缓存文件清理后即删", not os.path.isfile(_conv_dxf))
        else:
            # 异常防御分支验证
            _bad_dwg_caught = False
            try:
                convert_dwg_to_dxf(os.path.join(script_dir(), "non_existent.dwg"))
            except DwgConversionError:
                _bad_dwg_caught = True
            check("DWG 文件不存在时抛出 DwgConversionError 防御异常", _bad_dwg_caught)
    finally:
        _sh.rmtree(_td, ignore_errors=True)

    # 13. 模具自动开框(MOLD CUT)纯逻辑
    check("MOLD_BBOX_TOL 容差配置合法",
          isinstance(MOLD_BBOX_TOL, float) and MOLD_BBOX_TOL >= 0.0,
          str(MOLD_BBOX_TOL))
    check("MOLD_TRIAL_CUT 试切总开关为布尔(开=试切/关=直接减)",
          isinstance(MOLD_TRIAL_CUT, bool), str(MOLD_TRIAL_CUT))
    check("MOLD_AUDIT_VOLUME 体积对账开关为布尔(默认关以提速)",
          isinstance(MOLD_AUDIT_VOLUME, bool), str(MOLD_AUDIT_VOLUME))
    check("pair_hits 工具×模具配对预筛(命中/容差/残缺)",
          _pair_hits((0, 0, 0, 10, 10, 10),
                     [(5, 5, 5, 15, 15, 15), (20, 20, 20, 30, 30, 30), None])
          == [0]
          and _pair_hits(None, [(0, 0, 0, 1, 1, 1)]) == []
          and _pair_hits((0, 0, 0, 10, 10, 10), []) == []
          and _pair_hits((0, 0, 0), [(0, 0, 0, 1, 1, 1)]) == []
          and _pair_hits((0, 0, 0, 10, 10, 10), [(10.03, 0, 0, 20, 10, 10)],
                         0.05) == [0]
          and _pair_hits((0, 0, 0, 10, 10, 10), [(10.03, 0, 0, 20, 10, 10)],
                         0.0) == [])

    def _point_fail(_b, _p):
        raise RuntimeError("query failed")

    check("pick_points 采样点去重/region 优先/截断/残缺",
          _pick_points([(0, 0, 0), (0, 0, 0), (1, 1, 1)], 16)
          == [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]
          and _pick_points([(11, 11, 11), (0, 0, 0), (2, 2, 2)], 2,
                           (0, 0, 0, 10, 10, 10))
          == [(0.0, 0.0, 0.0), (2.0, 2.0, 2.0)]
          and _pick_points([(0, 0, 0), (0, 0, 0), (1, 1, 1)], 1)
          == [(0.0, 0.0, 0.0)]
          and _pick_points([], 16) == []
          and _pick_points([(0, 0, "x")], 16) == [])
    check("any_point_inside 命中/全外/全失败保守不剔除",
          _any_point_inside(lambda b, p: p[0] > 5, "B", [(0, 0, 0), (6, 0, 0)])
          is True
          and _any_point_inside(lambda b, p: False, "B", [(0, 0, 0)]) is False
          and _any_point_inside(_point_fail, "B", [(0, 0, 0)]) is True
          and _any_point_inside(lambda b, p: False, "B", []) is True)
    check("bbox_overlap 重叠/贴合/分离",
          _bbox_overlap((0, 0, 0, 10, 10, 10), (5, 5, 5, 15, 15, 15))
          and _bbox_overlap((0, 0, 0, 10, 10, 10), (10, 10, 10, 20, 20, 20))
          and not _bbox_overlap((0, 0, 0, 10, 10, 10),
                                (20, 20, 20, 30, 30, 30)))
    check("bbox_overlap 容差与残缺输入",
          _bbox_overlap((0, 0, 0, 10, 10, 10), (10.03, 0, 0, 20, 10, 10), 0.05)
          and not _bbox_overlap((0, 0, 0, 10, 10, 10),
                                (10.03, 0, 0, 20, 10, 10), 0.0)
          and not _bbox_overlap(None, (0, 0, 0, 1, 1, 1))
          and not _bbox_overlap((0, 0, 0), (0, 0, 0, 1, 1, 1))
          and not _bbox_overlap((0, 0, 0, "x", 1, 1), (0, 0, 0, 1, 1, 1)))
    check("merge_face_bboxes 合并与空残缺表",
          _merge_face_bboxes([(0, 0, 0, 4, 4, 4), (2, 2, 2, 9, 9, 9), None])
          == (0.0, 0.0, 0.0, 9.0, 9.0, 9.0)
          and _merge_face_bboxes([]) is None
          and _merge_face_bboxes([(0, 0, 0)]) is None
          and _merge_face_bboxes([(0, 0, 0, "x", 4, 4), (1, 1, 1, 2, 2, 2)])
          == (1.0, 1.0, 1.0, 2.0, 2.0, 2.0))
    _hole_ok = (None, 16, 7.5, 10.0, 0.0, -50.0,
                (2.5, -7.5, -70.0, 17.5, 7.5, -30.0))
    _hole_eaten = (None, 16, 7.5, 10.0, 0.0, -50.0,
                   (2.5, -7.5, -70.0, 17.5, 7.5, -45.0))
    check("broken_holes: 完好不误报/吃掉/缩边判冲突",
          _broken_holes([_hole_ok], [_hole_ok]) == []
          and len(_broken_holes([_hole_ok], [])) == 1
          and len(_broken_holes([_hole_ok], [_hole_eaten])) == 1
          and len(_broken_holes([_hole_ok], [_hole_ok, _hole_eaten])) == 0
          and _broken_holes([], [_hole_ok]) == []
          and _broken_holes(None, None) == [])
    check("hole_rows 只留曲面并容错残缺行",
          len(_hole_rows([(1, 20, 0.0, 0, 0, 0, (0, 0, 0, 1, 1, 1)),
                          (2, 16, 7.5, 1, 2, 3, (0, 0, 0, 9, 9, 9)),
                          None, (3, 16, "x")])) == 1
          and _hole_rows([]) == [] and _hole_rows(None) == [])
    check("mold rule 解析: 精确>关键词>类型默认",
          _rule_for("CX", [("CX", {"conflict_check": False, "blend_step_r": 5.0})])
          == {"conflict_check": False, "blend_step_r": 5.0}
          and _rule_for("STD:螺丝-45.prt",
                        [("STD:螺丝", {"conflict_check": True, "w": 1})])
          == {"conflict_check": True, "w": 1}
          and _rule_for("STD:其他.prt", []) == {"conflict_check": True}
          and _rule_for("FLB", []) == {"conflict_check": False}
          and _rule_for("", []) == {"conflict_check": False}
          and _kw_hits("STD:螺丝", "STD:螺丝-45.prt")
          and not _kw_hits("CX", "CX"))
    check("MOLD_CUT_RULES 配置行格式合法",
          all(isinstance(k, str) and isinstance(r, dict)
              for k, r in MOLD_CUT_RULES))
    check("is_sliver/grow/extents 薄片与包围盒工具",
          _is_sliver((0, 0, 0, 0.2, 3.0, 8.0), 5.0)
          and _is_sliver((0, 0, 0, 1.0, 1.0, 3.0), 5.0)
          and not _is_sliver((0, 0, 0, 15.0, 15.0, 0.0), 5.0)
          and not _is_sliver((0, 0, 0, 15.0, 15.0, 41.7), 5.0)
          and _grow((0, 0, 0, 10, 10, 10), 2.0) == (-2.0, -2.0, -2.0, 12.0, 12.0, 12.0)
          and _grow(None, 2.0) is None
          and _extents((0, 0, 0, 10, 20, 30)) == (10.0, 20.0, 30.0)
          and _extents(None) == (0.0, 0.0, 0.0))
    check("body_matches_bbox 按尺寸找体(中心定位片)",
          _body_matches_bbox((0, 0, 0, 15.0, 15.0, 41.7023),
                             [15.0, 15.0, 41.7023], 0.8)
          and _body_matches_bbox((0, 0, 0, 15.4, 14.8, 41.5),
                                 [15.0, 15.0, 41.7023], 0.8)
          and not _body_matches_bbox((0, 0, 0, 15.0, 15.0, 46.7),
                                     [15.0, 15.0, 41.7023], 0.8)
          and not _body_matches_bbox(None, [15, 15, 41.7], 0.8)
          and not _body_matches_bbox((0, 0, 0, 1, 1, 1), None, 0.8))

    # 13.x 布尔特征 with_failed 回归: 失败名单对账 + 失败工具体只减一次
    # (修复前: 单工具失败会在内部降级循环里被重复减第二次)
    class _MFeat:
        def __init__(self, tag):
            self.Tag = tag

        def SetName(self, _n):
            pass

    class _MBody:
        def __init__(self, tag):
            self.Tag = tag
            self.Name = ""

    class _MFeatures:
        def CreateSubtractFeature(self, _target, _a, tools, _retain, _b):
            self.calls.append(len(tools))
            if len(tools) > 1:
                raise RuntimeError("模拟本机 NX: 合并签名不符")
            if id(tools[0]) in self.ok_ids:
                return _MFeat(tools[0].Tag)
            raise RuntimeError("no intersection")

    class _MWorkPart:
        def __init__(self, ok_ids):
            f = _MFeatures()
            f.ok_ids = ok_ids
            f.calls = []
            self.Features = f

    _t_ok1, _t_ok2, _t_bad = _MBody(11), _MBody(12), _MBody(13)
    _wp = _MWorkPart({id(_t_ok1), id(_t_ok2)})
    _fs, _fd = _bool_feature(_wp, "subtract", None,
                             [_t_ok1, _t_bad, _t_ok2], "T",
                             lambda m: None, with_failed=True)
    _n0 = len(_wp.Features.calls)
    _fs1, _fd1 = _bool_feature(_wp, "subtract", None, [_t_bad], "T",
                               lambda m: None, with_failed=True)
    check("bool_feature with_failed: 失败名单对账+失败工具只减一次",
          len(_fs) == 2 and _fd == [_t_bad]
          and _fs1 == [] and _fd1 == [_t_bad]
          and len(_wp.Features.calls) - _n0 == 1
          and _wp.Features.calls[0] == 3,
          "calls=%s" % _wp.Features.calls)
    _fs2 = _bool_feature(_MWorkPart({id(_t_ok1)}), "subtract", None,
                         [_t_ok1], "T", lambda m: None)
    check("bool_feature 兼容: 默认(不带 with_failed)返回特征列表",
          isinstance(_fs2, list) and len(_fs2) == 1)

    # 13.x 合并减回滚保护回归: NX 多工具减可能已减入部分成员才抛异常,
    # session 在场时失败必须回滚(防"图上已减、日志报失败"账实不符)
    import types as _types_mod
    _nx = _types_mod.ModuleType("NXOpen")

    class _MarkVis:
        Invisible = 1

    class _NXSession:
        MarkVisibility = _MarkVis

    _nx.Session = _NXSession
    # 在 NX 会话内跑 --selftest 时(sys.modules 已有真实 NXOpen), 无条件 pop 会把
    # 真实模块摘掉, 后续任何 import NXOpen 的可用性不受控——先存后还(同 741 行
    # JRT 桩段的 _nx_keep 模式)
    _nx_keep = sys.modules.get("NXOpen")
    sys.modules["NXOpen"] = _nx
    try:
        class _MSession:
            def __init__(self):
                self.calls = []

            def SetUndoMark(self, _vis, _s):
                self.calls.append("mark")
                return 77

            def UndoToMark(self, _mk, _s):
                self.calls.append("undo")
                return True

        _sess_bad = _MSession()
        _fs3, _fd3 = _bool_feature(_wp, "subtract", None,
                                   [_t_ok1, _t_bad], "T",
                                   lambda m: None, with_failed=True,
                                   session=_sess_bad)
        check("bool_feature 合并减失败: 回滚部分效果后逐个对账",
              _sess_bad.calls == ["mark", "undo"]
              and len(_fs3) == 1 and _fd3 == [_t_bad],
              "calls=%s" % _sess_bad.calls)

        class _MFeaturesOk:
            def __init__(self):
                self.calls = []

            def CreateSubtractFeature(self, _target, _a, tools, _r, _b):
                self.calls.append(len(tools))
                return [_MFeat(99)]

        class _MWorkPartOk:
            def __init__(self):
                self.Features = _MFeaturesOk()

        _sess_ok = _MSession()
        _fs4, _fd4 = _bool_feature(_MWorkPartOk(), "subtract", None,
                                   [_t_ok1, _t_ok2], "T",
                                   lambda m: None, with_failed=True,
                                   session=_sess_ok)
        check("bool_feature 合并减成功: 只挂标记不回滚",
              _fd4 == [] and len(_fs4) == 1
              and _sess_ok.calls == ["mark"], str(_sess_ok.calls))

        # 13.x 批量删除回归(v2.4 提速): N 个对象一次全树更新, 失败降级逐个
        class _MUpdOk:
            def __init__(self):
                self.batches = []
                self.updates = 0

            def AddToDeleteList(self, objs):
                self.batches.append(len(objs))

            def DoUpdate(self, _mk):
                self.updates += 1

        class _MSessUpd:
            def __init__(self, upd):
                self.UpdateManager = upd

            def SetUndoMark(self, _v, _s):
                return 1

        _upd = _MUpdOk()
        _n3 = _batch_delete(_MSessUpd(_upd), ["a", "b", "c"],
                            lambda m: None, "测试")
        check("batch_delete 批量路径: N 对象合并一次更新",
              _n3 == 3 and _upd.batches == [3] and _upd.updates == 1,
              "batches=%s updates=%d" % (_upd.batches, _upd.updates))

        class _MUpdBad:
            def __init__(self):
                self.singles = 0

            def AddToDeleteList(self, objs):
                if len(objs) > 1:
                    raise RuntimeError("模拟批量删除被 NX 拒绝")
                self.singles += 1

            def DoUpdate(self, _mk):
                return 0

        class _MSessUpd2:
            def __init__(self):
                self.UpdateManager = _MUpdBad()

            def SetUndoMark(self, _v, _s):
                return 1

        _bd_msgs = []
        _sess_bd = _MSessUpd2()
        _n4 = _batch_delete(_sess_bd, ["a", "b"], _bd_msgs.append, "测试")
        check("batch_delete 降级路径: 批量失败自动转逐个删",
              _n4 == 2 and _sess_bd.UpdateManager.singles == 2
              and any("降级" in m for m in _bd_msgs))

        _n5 = _batch_delete(None, ["a"], lambda m: None, "空会话")
        check("batch_delete 空对象/空会话安全返回 0",
              _n5 == 0 and _batch_delete(_MSessUpd(_MUpdOk()), [],
                                         lambda m: None, "空") == 0)
    finally:
        if _nx_keep is None:
            sys.modules.pop("NXOpen", None)
        else:
            sys.modules["NXOpen"] = _nx_keep

    # 13.y v2.4 提速回归: 布尔计划分组 / 合并拉伸分组 / DWG 转换缓存
    _tg1, _tg2 = object(), object()
    _tools_a, _tools_b = [1], [2, 3]
    _grp = _group_bool_plan([
        (_tg1, "subtract", "甲.prt", 1, "SUBTRACT", _tools_a),
        (_tg2, "subtract", "乙.prt", 1, "SUBTRACT", _tools_b),
        (_tg1, "subtract", "甲.prt", 2, "PLACE_SUBTRACT", _tools_b),
        (_tg1, "unite", "丙.prt", 1, "UNITE", _tools_a),
    ])
    check("bool 计划按(目标,操作)保序分组(合并提交前提)",
          len(_grp) == 3
          and _grp[0][0] is _tg1 and _grp[0][1] == "subtract"
          and [(f, i) for f, i, _b, _t in _grp[0][2]]
          == [("甲.prt", 1), ("甲.prt", 2)]
          and _grp[1][0] is _tg2 and _grp[1][1] == "subtract"
          and _grp[2][0] is _tg1 and _grp[2][1] == "unite",
          "组数=%d" % len(_grp))

    _e1, _e2, _e3 = {"pick": _tg1}, {"pick": _tg1}, {"pick": None}
    check("merge_groups: subtract 按目标分组+无目标独立组",
          _merge_groups("subtract", [_e1, _e2, _e3])
          == [(_tg1, [_e1, _e2]), (None, [_e3])])
    check("merge_groups: 非 subtract 全并一组",
          _merge_groups("none", [_e1, _e2]) == [(None, [_e1, _e2])])
    check("merge_groups: 空表安全", _merge_groups("subtract", []) == []
          and _merge_groups("none", []) == [(None, [])])
    check("合并拉伸开关默认开 + 日志后缀",
          _merge_extrude_enabled() is True
          and _merge_note(True) == ", 多个轮廓一次拉伸"
          and _merge_note(False) == "")

    from cad3d.geom import dwg_converter as _dwc
    _td2 = _tf.mkdtemp(prefix="cad3d_dwgcache_")
    _src_dwg = os.path.join(_td2, "样图.dwg")
    _cache_probe = None
    try:
        with io.open(_src_dwg, "wb") as f:
            f.write(b"FAKE-DWG-1")
        os.utime(_src_dwg, (1000000000, 1000000000))
        _ka = _dwc._dwg_cache_key(_src_dwg)
        check("DWG 缓存键: 同路径同大小同时间稳定",
              _ka == _dwc._dwg_cache_key(_src_dwg) and len(_ka) == 16)
        with io.open(_src_dwg, "wb") as f:
            f.write(b"FAKE-DWG-2")      # 同长度不同内容
        os.utime(_src_dwg, (1000000000, 1000000000))
        _same = _dwc._dwg_cache_key(_src_dwg)
        with io.open(_src_dwg, "ab") as f:
            f.write(b"X")               # 大小变化
        _kb = _dwc._dwg_cache_key(_src_dwg)
        os.utime(_src_dwg, (1000000900, 1000000900))
        _kc = _dwc._dwg_cache_key(_src_dwg)
        check("DWG 缓存键: 大小/mtime 变化即失配(改图自动重转)",
              _same == _ka and _kb != _ka and _kc != _kb)
        check("is_cache_dxf 前缀判定",
              _dwc.is_cache_dxf(os.path.join("logs", "_dwg_cache_ab12.dxf"))
              and not _dwc.is_cache_dxf(os.path.join("logs", "_temp_dwg_x.dxf"))
              and not _dwc.is_cache_dxf("")
              and not _dwc.is_cache_dxf(None))

        _cache_probe = _dwc._cache_path_for(_src_dwg)
        with io.open(_cache_probe, "wb") as f:
            f.write(b"  0\nSECTION\n  2\nENTITIES\n")
        check("DWG 缓存命中: 同图直接复用缓存文件",
              _dwc.lookup_dwg_cache(_src_dwg) == _cache_probe)
        with io.open(_cache_probe, "wb") as f:
            f.write(b"")
        check("DWG 缓存未命中: 空文件忽略", _dwc.lookup_dwg_cache(_src_dwg) is None)
        with io.open(_cache_probe, "wb") as f:
            f.write(b"garbage-not-dxf")
        check("DWG 缓存未命中: 损坏文件不进流水线",
              _dwc.lookup_dwg_cache(_src_dwg) is None)
        with io.open(_cache_probe, "wb") as f:
            f.write(b"  0\nSECTION\n")
        _orig_ce = _dwc._cache_enabled
        _dwc._cache_enabled = lambda: False
        try:
            check("DWG 缓存未命中: 开关关闭(DWG_CACHE_ENABLE=False)",
                  _dwc.lookup_dwg_cache(_src_dwg) is None)
        finally:
            _dwc._cache_enabled = _orig_ce
        check("DWG 缓存未命中: 图纸文件不存在",
              _dwc.lookup_dwg_cache(os.path.join(_td2, "无此图.dwg")) is None)

        _stale = os.path.join(_logs_dir(), "_dwg_cache_stale_selftest.dxf")
        with io.open(_stale, "wb") as f:
            f.write(b"  0\nSECTION\n")
        _old_t = time.time() - 8 * 86400
        os.utime(_stale, (_old_t, _old_t))
        _dwc._clean_stale_temp_files()
        check("DWG 缓存过期自动清理(默认 7 天)", not os.path.isfile(_stale))
    finally:
        for _pf in (_cache_probe,):
            if _pf and os.path.isfile(_pf):
                try:
                    os.remove(_pf)
                except OSError:
                    pass
        _sh.rmtree(_td2, ignore_errors=True)

    # 12. 真实图纸(可选)
    real = dxf_path
    if not real:
        cand = os.path.join(script_dir(), "Drawing5.dxf")
        real = cand if os.path.isfile(cand) else None
    if real:
        layers_r, stats_r = parse_dxf(real)
        print("[INFO] %s: 实体 %d, 图层 %s, 参考(不建模) %s" % (
            os.path.basename(real), stats_r["total"],
            {k: len(v) for k, v in layers_r.items()}, stats_r["ref_layers"]))
    print("SELFTEST %s" % ("OK" if ok else "FAILED"))
    return ok
