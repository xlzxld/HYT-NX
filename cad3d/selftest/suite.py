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
    script_dir, _fresh_dlx_path, _json_path, _temp_dlx_path, resolve_dxf_path
)
from cad3d.core.config import (
    _CFG_NOTES, _cfg, _cfg_num, _cfg_int, _USER_CFG, SCHEMA_VERSION
)
from cad3d.core.constants import (
    _LINK_OFFSETS, JRT_FROM_TOP, DEFAULT_JRT, MANAGED_MAX, STDPARTS_DIRNAME,
    JT_LINK_DEFAULT, JRT_FIELDS, LAYER_SEL_OPTS, BOOL_OPTS, ZMODE_OPTS,
    _ZMODE_FALLBACK, _ZMODE_DEFS, STD_MAX_ANCHORS, LAYER_CODES, DIR_OPTS,
    assign_layers
)
from cad3d.core.state import (
    _jt_link_values, jt_mode_with_memory, _cx_link_values, derive_linked,
    jrt_with_memory, default_params, load_state, _name_list, save_state,
    merge_params, merge_jrt
)
from cad3d.core.logging import Log
from cad3d.geom.entities import DXLine, DXArc, DXCircle
from cad3d.geom.dxf_parser import parse_dxf
from cad3d.geom.topo import (
    find_chains, loop_polygon, poly_area, _bbox, point_in_poly,
    _loop_in_loop, organize_loops, _chain_tips, _cluster_tips,
    _merge_open_chains, _center_seen, collect_circle_anchors,
    _chain_outlet_mids, _chain_connectors
)
from cad3d.geom.eval import (
    _dxf_ent_fp, dxf_fingerprints, _faces_healthy, _flush_start_r,
    _dome_body_ok, _blend_ok, _conn_face_pick, _jrt_sides
)
from cad3d.modeling.std_rules import (
    _std_z, std_part_defaults, guess_std_rule, sanitize_std_rule, _rule_usable,
    _unusable_names, discover_std_parts, merge_std_rules, anchors_overflow
)
from cad3d.modeling.stdparts import _place_delta
from cad3d.modeling.extrude import modeling_ents, build_layer
from cad3d.ui.dlx_builder import (
    _blk_enum, build_dlx, build_selection_dlx, build_std_dlx, _group_item,
    _blk_label
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
    sample = os.path.join(script_dir(), ".zcode", "sample_layers.dxf")
    try:
        os.makedirs(os.path.dirname(sample), exist_ok=True)
    except OSError:
        pass
    make_sample_dxf(sample)
    layers, stats = parse_dxf(sample)
    check("合成 DXF 各层曲线数",
          len(layers.get("FLB", [])) == 8 and len(layers.get("LS", [])) == 4
          and len(layers.get("DP", [])) == 8 and len(layers.get("RZ", [])) == 2,
          str({k: len(v) for k, v in layers.items()}))
    check("JRT 参考图层导入", len(layers.get("JRT", [])) == 4)
    check("LD 参考图层导入", len(layers.get("LD", [])) == 1)
    mp = assign_layers(["LD", "0", "FLB", "JRT"])
    check("动态图层号分配", mp["FLB"] == _cfg("NX_LAYER_START", 11)
          and mp["JRT"] == _cfg("NX_LAYER_JRT", 18)
          and mp["0"] == _cfg("NX_LAYER_DYNAMIC_START", 19)
          and mp["LD"] == _cfg("NX_LAYER_DYNAMIC_START", 19) + 1,
          str(mp))
    _lo_cfg = _cfg("LINK_OFFSETS", {})
    if not isinstance(_lo_cfg, dict):
        _lo_cfg = {}
    check("联动/JRT建模/图层号均来自 config(v1.33)",
          _LINK_OFFSETS == {k: _cfg_num(_lo_cfg.get(k), d)
                            for k, d in (("RZ", 13.0), ("DK", 3.0),
                                         ("DP", 6.7023))}
          and JRT_FROM_TOP == _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)
          and DEFAULT_JRT["offset"] == _cfg_num(_cfg("JRT_OFFSET", 5.0), 5.0)
          and DEFAULT_JRT["draft"] == _cfg_num(_cfg("JRT_DRAFT", 2.0), 2.0)
          and DEFAULT_JRT["color_strip"] == _cfg_int("JRT_COLOR_STRIP", 186)
          and MANAGED_MAX == _cfg_int("NX_LAYER_MAX", 70)
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
          d["LS"] == (-40.0, -90.0) and d["RZ"] == (-77.0, -90.0)
          and d["DK"] == (-40.0, -43.0)
          and abs(d["DP"][0] - -83.2977) < 1e-9 and d["DP"][1] == -90.0
          and d["JRT"] == (-40.0, -47.5), str(d))
    d2 = derive_linked(45.0, 0.0)
    check("联动推导 正 Z 参数",
          d2["RZ"] == (13.0, 0.0) and d2["DK"] == (45.0, 42.0)
          and d2["DP"] == (6.7023, 0.0) and d2["JRT"] == (45.0, 37.5))

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
          and dp["RZ"] == (-72.0, -85.0) and dp["DK"] == (-40.0, -43.0)
          and dp["LS"] == (-40.0, -85.0) and dp["DP"][0] == -78.2977)
    check("jt 模式记忆恢复", jt_mode_with_memory(
        {"jt_link_mode": "针阀模式"}) == "针阀模式")
    check("jt 模式记忆无效回默认",
          jt_mode_with_memory({"jt_link_mode": "不存在"}) == JT_LINK_DEFAULT)
    check("jt 模式无记忆回默认", jt_mode_with_memory({}) == JT_LINK_DEFAULT)
    check("窗口② dlx 含 JT 联动下拉",
          "jt_link" in build_dlx(default_params(), dict(DEFAULT_JRT),
                                 jt_mode="普通模式"))

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
    check("猜测: 大水口→RZ/FLB底", g2["layer"] == "RZ"
          and g2["z_mode"] == "FLB_BOTTOM")
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
    check("_blend_ok: 测不到不拦", _blend_ok(None, None))

    _rows = [(1, 10.0, 10.0, 3.9), (2, 10.0, 40.0, 3.9), (3, 50.0, 10.0, 3.9),
             (4, 10.0, 10.0, 300.0)]
    check("删面: 半径匹配+距离近→选中",
          _conn_face_pick(_rows, [(10.2, 10.0), (10.0, 39.8)], 3.9) == [1, 2])
    check("删面: 只有错半径面→放弃",
          _conn_face_pick([(1, 10.0, 10.0, 300.0)], [(10.0, 10.0)], 3.9) is None)
    check("删面: 距离超门控→放弃",
          _conn_face_pick([(1, 50.0, 50.0, 3.9)], [(10.0, 10.0)], 3.9) is None)
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
              rr["layer"] in LAYER_CODES + ["CXK", ""]
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

    real2 = os.path.join(script_dir(), "3Dtest.dxf")
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
    profs_dpx, opens_dp, _ = organize_loops(layers["DP"])
    check("DP 垫片嵌套", len(profs_dpx) == 1 and len(profs_dpx[0]["holes"]) == 1)
    profs_flb, _o, _c = organize_loops(layers["FLB"])
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
        check("resolve_dxf_path 传 None/坏类型容错",
              resolve_dxf_path(None) == "" and resolve_dxf_path(123) == "")
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
    finally:
        _sh.rmtree(_td, ignore_errors=True)

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
