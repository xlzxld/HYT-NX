# -*- coding: utf-8 -*-
"""
nx_selftest.py —— 自测 / 合成 DXF / 未定义名称静态检查(离线, 无 NX 依赖)
========================================================================

拆分自 nx_extrude_runner.py(§7 自测区)。不 import NXOpen, 可 `--selftest`
离线跑。

依赖契约: 本模块引用主脚本的绝大多数符号(几何/规则/联动/dlx/指纹…),
故由主脚本以"注入整个命名空间"方式提供(见 nx_extrude_runner.py 的加载段)。
_st 里的 _undefined_name_check 支持 extra_names 参数, 用于把"注入名"排除在
未定义名检查之外。
"""

import io
import os


def make_sample_dxf(path):
    """生成 7 图层合成测试 DXF(覆盖: 多环/圆/嵌套垫片/贯穿 subtract)。"""

    def rect(layer, x, y, w, h):
        out = []
        for (x1, y1, x2, y2) in [(x, y, x + w, y), (x + w, y, x + w, y + h),
                                 (x + w, y + h, x, y + h), (x, y + h, x, y)]:
            out += ["0", "LINE", "8", layer, "10", "%.3f" % x1, "20", "%.3f" % y1,
                    "30", "0", "11", "%.3f" % x2, "21", "%.3f" % y2, "31", "0"]
        return out

    def circle(layer, cx, cy, r):
        return ["0", "CIRCLE", "8", layer, "10", "%.3f" % cx, "20", "%.3f" % cy,
                "30", "0", "40", "%.3f" % r]

    body = ["0", "SECTION", "2", "ENTITIES"]
    body += rect("FLB", 0, 0, 200, 40)        # 通道 1
    body += rect("FLB", 0, 80, 200, 40)       # 通道 2(多体 unite 场景)
    body += rect("JT", 250, 0, 120, 60)
    for (cx, cy) in [(10, 10), (190, 10), (10, 30), (190, 30)]:
        body += circle("LS", cx, cy, 4.25)
    body += circle("RZ", 100, 20, 11.35)
    body += circle("DK", 100, 20, 3.0)        # 与 RZ 同心(嵌套 subtract 场景)
    body += circle("RZ", 100, 100, 11.35)
    body += circle("DK", 100, 100, 3.0)
    body += rect("DP", 0, -80, 60, 60)        # 垫片外环
    body += rect("DP", 10, -70, 40, 40)       # 垫片内环(同层嵌套→孔)
    body += rect("CX", 0, 160, 30, 10)
    body += rect("JRT", 0, 220, 120, 30)     # 参考图层(只导入不拉伸)
    body += ["0", "LINE", "8", "LD", "10", "0", "20", "-30", "30", "0",
             "11", "0", "21", "-31", "31", "0"]   # 动态分配图层的参考线
    body += ["0", "ENDSEC", "0", "EOF"]

    with io.open(path, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(body))
    return path


def _undefined_name_check(path, extra_names=()):
    """AST 静态检查: 模块内所有 Name 引用是否可解析(模块级/内建/作用域链)。

    捕捉"交互路径才炸"的拼写 NameError(教训: build_selection_dxl 笔误,
    批量冒烟走不到 main() 交互路径未暴露)。嵌套函数可见外层局部名;
    global 声明的名视为已解析(可能在别处赋值)。

    (P4) extra_names: 由主脚本注入的符号名集。拆分后子模块的函数引用注入名
    (如 LAYER_CODES/_std_z), 这些名不在子模块源码里定义, 需经本参数豁免,
    否则误报。主脚本注入的是"整个主命名空间", 故按主模块公开名全集传即可。
    """
    import ast
    import builtins

    with io.open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    module_names = set(dir(builtins)) | {"__name__", "__file__"} | set(extra_names)
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
                local.add(n.name)   # 函数内定义的类同样绑定局部名(v1.35)
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
    import xml.etree.ElementTree as ET        # dlx 良构校验(全函数共用)

    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            ok = False

    for _n in notes():             # 配置缺失/损坏在这里可见, 不静默回退
        print("[INFO] 配置提示: %s" % _n)

    # 0. AST 未定义名称检查(防交互路径 NameError; 改名/删函数后必查)。
    #    (P4) 拆分后扩展到所有模块: 主脚本 + 各子模块。子模块里引用注入名,
    #    以主脚本公开名全集 INJECTED_NAMES 豁免(见 _undefined_name_check)。
    _inj = globals().get("INJECTED_NAMES") or set()
    for _f in ("nx_extrude_runner.py", "nx_geom.py", "nx_rules.py",
               "nx_dlx.py", "nx_selftest.py",
               "nx_jrt_geom.py", "nx_jrt.py",
               "nx_nxcore.py", "nx_stdparts.py"):
        _p = os.path.join(script_dir(), _f)
        if not os.path.isfile(_p):
            continue
        _bad = _undefined_name_check(_p, extra_names=_inj)
        check("AST 未定义名称=0 [%s]" % _f, not _bad, "; ".join(_bad[:6]))

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

    # 3b. 三层嵌套(孔中岛): 岛须独立成体, 不能当成第二个孔被减掉
    #     (v1.29 修复: parent 取"最小包含环"; 此前取到最大环→岛被判成 A 的
    #      第二个孔, 岛的材料被一并减掉, 与 2D 图不符)
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
    # 3c. 四层嵌套: 外环带1孔 + 岛再带1孔
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

    # 6. 几何指纹(清理迁移匹配的纯逻辑部分)
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

    # 7. JRT 侧向区间(纯逻辑; 新签名 start/end + 底侧镜像)
    sides = _jrt_sides(-40.0, -47.5, -85.0)
    check("JRT 两侧区间(负 Z)",
          sides == [("T", -40.0, -47.5), ("B", -85.0, -77.5)], str(sides))
    sides2 = _jrt_sides(45.0, 37.5, 0.0)
    check("JRT 两侧区间(正 Z)",
          sides2 == [("T", 45.0, 37.5), ("B", 0.0, 7.5)], str(sides2))
    # v1.9: JRT 恒默认不持久化(JSON 漂移污染的根治; start/end 由 FLB 联动)
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

    # 7c. enum Value 属性写入选中序号(修复"全部卡第0项"的关键)
    en = _blk_enum("t", "测试", ["甲", "乙", "丙"], 2)
    check("enum Value=选中序号", 'sname="TEMPVALUE" source="1" type="integer" value="2"'
          in en)
    # dlx 加热条组
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

    # id 往返校验(v1.6 教训: dlx 块 id 与收集构造不一致 → 参数永远失效)
    for key, _label in JRT_FIELDS:
        check("JRT id 往返 jrt_%s" % key,
              ('value="jrt_%s"' % key) in xml3)
    # 7d. 标准件规则引擎(纯逻辑; v1.9 默认值表驱动)
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
    # CX+CXK 合并闭环(2D 新规则: CX 单独开口, CXK 补线成环)
    cx_open = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
               DXLine((10, 5), (0, 5))]
    lay_m = {"CX": cx_open, "CXK": [DXLine((0, 5), (0, 0))]}
    me = modeling_ents(lay_m, "CX")
    profs_m, opens_m, _ = organize_loops(me)
    check("CX+CXK 并入成环", len(me) == 4 and len(profs_m) == 1 and not opens_m)
    check("非 CX 层不并入 CXK",
          len(modeling_ents({"JT": cx_open, "CXK": lay_m["CXK"]}, "JT")) == 3)
    # 顶面靠后边缘中点(纯逻辑; 三型号实测面数据回放)
    # v1.15 防卡死护栏(nx_std_config.STD_MAX_ANCHORS + 特征指纹)
    check("护栏: 数量超限", anchors_overflow(
        list(range(201)), sanitize_std_rule({})))
    check("护栏: 正常数量不超限", not anchors_overflow(
        list(range(8)), sanitize_std_rule({"layer": "LS", "r_max": 5})))
    check("护栏: 空图层+大半径=指纹拦截(卡死案规则)",
          anchors_overflow(list(range(47)),
                           sanitize_std_rule({"layer": "", "r_max": 9999})))
    # v1.17 开链修复(123.dxf: 0.24mm 接缝两条链该合并; 25mm 缺口该桥接)
    _oe = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5)),                       # 链1: 缺左边(断口(0,0),(0,5))
           DXLine((0, 5.2), (0.2, 5.2)), DXLine((0.2, 5.2), (0.2, 0.2)),
           DXLine((0.2, 0.2), (0, 0.2))]                  # 链2 三段折线, 断口(0,5.2),(0,0.2)
    _ce, _bj, _ol = _merge_open_chains(
        [[(0, False), (1, False), (2, False)],
         [(3, False), (4, False), (5, False)]], _oe, tol=0.5, bridge_max=0.5)
    check("开链修复: 近缝两链合并→2条接缝桥(≤0.5)",
          len(_ce) == 0 and len(_bj) == 1 and len(_bj[0][1]) == 2, str(_bj))
    _e2 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (0, 5))]                        # 缺 10mm 左边
    _ce2, _bj2, _ol2 = _merge_open_chains([[(0, False), (1, False), (2, False)]],
                                          _e2, tol=0.5)
    check("开链修复: 5mm 缺口→放弃记日志(直线桥大缺口=怪条一案)",
          not _ce2 and not _bj2 and len(_ol2) == 1, str((_ce2, _bj2, _ol2)))
    _ce3, _bj3, _ol3 = _merge_open_chains([[(0, False)]], [DXLine((0, 0), (10, 0))],
                                          tol=0.5)
    check("开链修复: 10mm 缺口→放弃", len(_bj3) == 0 and len(_ol3) == 1)
    # 泛化: 1 接缝簇 + 2 单点簇(3Dtest 实际形态)→ 2 条桥全闭合
    _e5 = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (10, 5)),
           DXLine((10, 5), (10, 5.065)), DXLine((10, 5.065), (0, 5.065)),
           DXLine((0, 0.2), (0, 4.8))]     # 右上0.065接缝 + 左边缺0.2~4.8
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
    # v1.17 倒圆异形检测(体积校验)
    check("_blend_ok: 丢体11%=正常(基准样板实证)",
          _blend_ok(41049.5, 36553.8))
    # v1.23 面体检(jrt1 好条=全解析; 01 坏条=样条面/碎片面)
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
    # v1.17 删面收紧(圆柱面半径匹配+距离门控; 期刊面中心距连接线≈1)
    _rows = [(1, 10.0, 10.0, 3.9), (2, 10.0, 40.0, 3.9), (3, 50.0, 10.0, 3.9),
             (4, 10.0, 10.0, 300.0)]                    # 第4个=巨R非倒圆面
    check("删面: 半径匹配+距离近→选中",
          _conn_face_pick(_rows, [(10.2, 10.0), (10.0, 39.8)], 3.9) == [1, 2])
    check("删面: 只有错半径面→放弃",
          _conn_face_pick([(1, 10.0, 10.0, 300.0)], [(10.0, 10.0)], 3.9) is None)
    check("删面: 距离超门控→放弃",
          _conn_face_pick([(1, 50.0, 50.0, 3.9)], [(10.0, 10.0)], 3.9) is None)
    check("护栏: 全图层但半径收窄→放行(压线板式需求)",
          not anchors_overflow(list(range(47)),
                               sanitize_std_rule({"layer": "", "r_max": 20})))
    # 以下三项依赖外部配置; nx_std_config.py 缺失时应跳过而非崩
    # (v1.29: 配置按设计是可选的, 缺失走内置兜底表, 自测不该因此 AttributeError)
    cfg = _USER_CFG
    check("BOOL_OPTS 无停用项", all(b[0] != "OFF" for b in BOOL_OPTS))
    if cfg is None:
        # 配置缺失走内置回退, 不得 AttributeError 崩溃(v1.29 声明; v1.35 补守卫)
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
    _n_zm_before = len(zmode_defs())
    with temporary_zmode(("JT_BOTTOM", "JT底面", "JT", "BOTTOM")):
        _ok_new = _std_z({"FLB": (-40.0, -90.0), "JT": (-30.0, -100.0)},
                         sanitize_std_rule({"z_mode": "JT_BOTTOM"}))
    check("_std_z 查表: 动态加基准(JT底→-100)即加即用", _ok_new == -100.0)
    check("temporary_zmode 退出后 Z 基准表已还原(不污染后续)",
          len(zmode_defs()) == _n_zm_before
          and all(d[0] != "JT_BOTTOM" for d in zmode_defs()))
    check("_rule_usable: 无ref不可用",
          not _rule_usable({"ref": None})
          and not _rule_usable({"ref": [1, 2]})
          and _rule_usable({"ref": [1.0, 2.0, 3.0]}))
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
    # 期刊 journal-djk.py 地面真值: 点胶口-18 起始点 (1594.78,-395.73,-570.189)
    # jrt 记忆: start/end 有记忆用记忆; 无记忆按 FLB 联动; 三参数恒默认
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
    import inspect as _insp
    check("save_state 支持 jrt_se 字段",
          "jrt_se" in _insp.signature(save_state).parameters)
    check("save_state 支持 jt_link_mode 字段",
          "jt_link_mode" in _insp.signature(save_state).parameters)
    # 配置表归用户维护(压线板已由用户自行加入), 通用默认路径用保证
    # 不在表中的名字测试
    # v1.24 连接线泛化(01.dxf 环形通道: 4 条等长 6.09 跨接线)
    _ring = [DXLine((483.5, 84.9), (483.5, 91.0)),    # 跨接线
             DXLine((483.5, 91.0), (491.5, 91.0)),    # 出线口线(8mm)
             DXLine((491.5, 91.0), (491.5, 84.9)),    # 跨接线
             DXArc((500.0, 84.9), 8.5, 0, math.pi),   # 底部过渡弧
             DXLine((508.5, 84.9), (508.5, 91.0)),
             DXLine((516.5, 91.0), (508.5, 91.0)),    # 出线口线(8mm)
             DXLine((516.5, 91.0), (516.5, 84.9)),
             DXArc((500.0, 84.9), 16.5, math.pi, 0)]  # 顶部大弧闭环
    _ring_ch = [(i, False) for i in range(len(_ring))]
    _rc = _chain_connectors(_ring_ch, _ring)
    check("连接线泛化: 环形通道4条跨接线",
          len(_rc) == 4, str(_rc))
    _om = _chain_outlet_mids(_ring_ch, _ring)
    check("出线口线中点: 2条口线(期刊删除面锚点)",
          len(_om) == 2
          and any(abs(m[0] - 487.5) < 0.01 for m in _om)
          and any(abs(m[0] - 512.5) < 0.01 for m in _om), str(_om))
    # v1.29 参考点自助配置
    check("sanitize ref: 合法3数保留",
          sanitize_std_rule({"ref": [1, 2.5, -3]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 数字字符串转float",
          sanitize_std_rule({"ref": ["1", "2.5", "-3"]})["ref"] == [1.0, 2.5, -3.0])
    check("sanitize ref: 非3长/坏值/缺失→None",
          sanitize_std_rule({"ref": [1, 2]})["ref"] is None
          and sanitize_std_rule({"ref": [1, "x", 3]})["ref"] is None
          and sanitize_std_rule({})["ref"] is None)
    set_stdparts_lister(lambda: ["垫片.prt"])
    try:
        _mr = merge_std_rules({"schema": SCHEMA_VERSION,
                               "std_parts": {"垫片.prt": {
                                   "layer": "DK", "ref": [7, 8, 9]}}})
    finally:
        set_stdparts_lister(None)
    check("记忆往返: ref 不丢",
          _mr["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])
    _rt = json.loads(json.dumps(_mr))
    _mr2 = merge_std_rules({"schema": SCHEMA_VERSION, "std_parts": _rt})
    check("json 往返: ref 不丢", _mr2["垫片.prt"]["ref"] == [7.0, 8.0, 9.0])
    # v1.26 厚度预防式起试半径
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
    # JSON 记忆 schema 守卫(版本不符全忽略防污染; 调大 CONFIG_SCHEMA_VERSION
    # 即可清洗旧规则记忆——点胶口 z_mode/垫片 bool 脏数据一案)
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
    set_stdparts_lister(lambda: ["垫片.prt"])
    try:
        m_stale = merge_std_rules({"schema": SCHEMA_VERSION - 1,
                                   "std_parts": {"垫片.prt": {"layer": "LS"}}})
        m_ok = merge_std_rules({"schema": SCHEMA_VERSION,
                                "std_parts": {"垫片.prt": {"layer": "LS"}}})
    finally:
        set_stdparts_lister(None)
    check("JSON 记忆 schema 守卫",
          m_stale["垫片.prt"]["layer"] == "DK"
          and m_ok["垫片.prt"]["layer"] == "LS")
    # 选择对话框 dlx(两段式第一段)
    sxml = build_selection_dlx(["a.prt", "b.prt"], ["b.prt"])
    try:
        ET.fromstring(sxml)
        check("选择对话框 dlx 良构", True)
    except ET.ParseError as ex:
        check("选择对话框 dlx 良构", False, str(ex))
    check("选择对话框 toggle=2 且 b 选中",
          sxml.count('class="UICOMP_toggle" hierarchy="UGS::UICOMP_group"') == 2
          and 'id="SEL1"' in sxml)

    # 8. JRT 收口连接线识别(真实 3Dtest.dxf; 期刊删面位置=连接线中点旁)
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

    # 9. dlx 生成 + XML 良构
    xml = build_dlx(default_params())
    try:
        ET.fromstring(xml)
        check("dlx XML 良构", True)
    except ET.ParseError as ex:
        check("dlx XML 良构", False, str(ex))
    dbl = xml.count('<item Expanded="1" class="UICOMP_double"')
    check("dlx double 块数=19(图层14+JRT5)", dbl == 19, "got %d" % dbl)

    # 10. 标准件规则与锚点(纯逻辑)
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

    # 11. 窗口② dlx: 标准件组已在 v1.35 删除(参数页只在窗口③ build_std_dlx)
    xml2 = build_dlx(default_params(), dict(DEFAULT_JRT))
    check("窗口②无标准件组(v1.35 休眠段删除)",
          'id="grp_std"' not in xml2 and "SP0_" not in xml2
          and 'id="jrt_start"' in xml2)
    # 三段式: 窗口②无标准件组; 窗口③每件一个可收起组
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

    # 11b. v1.35 审计修复回归断言(边界/异常/压力)
    import tempfile as _tf
    import shutil as _sh
    _td = _tf.mkdtemp(prefix="cad3d_selftest_")
    try:
        # 边界: 空 DXF / 不支持实体统计(LWPOLYLINE 不静默丢)
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
        # 边界: 断口 0.006(<容差) 但跨量化格边界 → 邻桶搜索仍连链
        _gl = [DXLine((0, 0), (10.0, 0.0)), DXLine((9.994, 0.0), (20.0, 0.0))]
        _gc, _go = find_chains(_gl)
        check("格点边界断口仍能连链(邻桶)",
              not _gc and len(_go) == 1 and len(_go[0]) == 2)
        # 边界: T 形三叉 → 直线延续优先, 不串进垂线
        _tj = [DXLine((0, 0), (10, 0)), DXLine((10, 0), (20, 0)),
               DXLine((10, 0), (10, 10))]
        _tc, _to = find_chains(_tj)
        check("T形三叉: 直线延续优先(不串错链)",
              not _tc and len(_to) == 2 and {i for i, _r in _to[0]} == {0, 1})
        # 边界: 双重描线的重复环 → 去重, 不被误判为孔
        _dp, _do, _ = organize_loops(_sq(0, 0, 100, 100) + _sq(0, 0, 100, 100))
        check("重复描线环去重(不被误判为孔)",
              len(_dp) == 1 and not _dp[0]["holes"], "profiles=%d" % len(_dp))
        # 正确性: -Z 翻转件放置位移(ref 的 y/z 随姿态反号)
        check("-Z 放置位移(ref 随姿态旋转)",
              _place_delta((10.0, 2.0, 3.0), False, (1.0, 1.0, 1.0))
              == (-9.0, -1.0, -2.0)
              and _place_delta((10.0, 2.0, 3.0), True, (1.0, 1.0, 1.0))
              == (-9.0, 3.0, 4.0))
        # 异常: merge_params 坏类型不崩 + schema 门控 params(文档口径)
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
        # 异常: 坏 JSON 记忆隔离留证 + save_state 原子写(临时目录, 猴补路径)
        _bad = os.path.join(_td, "nx_extrude_params.json")
        with io.open(_bad, "w", encoding="utf-8") as _f:
            _f.write("{oops not json")
        _ok_iso = _ok_atomic = False
        set_json_path_provider(lambda: _bad)
        try:
            _st = load_state()
            _ok_iso = (isinstance(_st, dict) and not _st and
                       [n for n in os.listdir(_td)
                        if n.startswith("nx_extrude_params.json.bad-")] != [])
        finally:
            set_json_path_provider(None)
        check("坏 JSON 记忆隔离留证(.bad-*)", _ok_iso)
        set_json_path_provider(lambda: _bad)
        try:
            save_state("X:/a.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2))
            _st2 = load_state()
            _ok_atomic = (_st2.get("dxf_path") == "X:/a.dxf"
                          and _st2.get("selected") == ["a.prt"]
                          and not [n for n in os.listdir(_td)
                                   if n.endswith(".tmp")])
        finally:
            set_json_path_provider(None)
        check("save_state 原子写+类型容错", _ok_atomic)
        # jt_link_mode 传 None → 保留旧记忆里的模式(v1.38 修复)
        _jp3 = os.path.join(_td, "jt_mem_test.json")
        if os.path.isfile(_jp3):
            os.remove(_jp3)
        set_json_path_provider(lambda: _jp3)
        try:
            save_state("X:/a.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2),
                       jt_link_mode="针阀模式")
            save_state("X:/b.dxf", {"FLB": (1.0, 2.0)},
                       selected=["a.prt"], jrt_se=(1, 2))
            _st3 = load_state()
        finally:
            set_json_path_provider(None)
        check("jt_link_mode 传 None 保留旧值(v1.38)",
              _st3.get("jt_link_mode") == "针阀模式"
              and _st3.get("dxf_path") == "X:/b.dxf")
        try:
            os.remove(_jp3)
        except OSError:
            pass
        # 异常: _find 对 None 不缓存(可重试)
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
        # 压力: 锚点收集 4000 实体(2000 重复) <2s 且去重正确
        _big = {"RZ": [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                       for i in range(2000)]
                + [DXCircle((float(i % 100) * 10.0, float(i // 100) * 10.0), 5.0)
                   for i in range(2000)]}
        _t0 = time.time()
        _ab = collect_circle_anchors(_big, sanitize_std_rule({"layer": "RZ"}))
        _dt = time.time() - _t0
        check("锚点去重 4000 实体 <2s 且去重正确",
              len(_ab) == 2000 and _dt < 2.0, "%.3fs" % _dt)
        # 压力: 200 个互不嵌套矩形组织 <3s
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
