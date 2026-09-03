# -*- coding: utf-8 -*-
"""
nx_rules.py —— 标准件规则 / 分层联动 / 参数记忆(纯逻辑, 无 NX 依赖)
========================================================================

拆分自 nx_extrude_runner.py(§0 规则与联动函数 + §4 参数记忆 + §5 里的放置
/锚点/Z 基准纯逻辑)。本模块不 import NXOpen, 可离线单测。

依赖契约(由主脚本注入为模块属性, 见 docs/模块拆分实施计划.md §1)。下列名字
均为"主脚本在 §0 算出的常量/函数", 本模块函数在调用时经模块全局字典取用:
    script_dir STDPARTS_DIRNAME DEFAULT_STD_RULE DEFAULT_JRT STD_MAX_ANCHORS
    SCHEMA_VERSION _USER_CFG LAYER_CODES LAYER_TABLE TARGET_CODE LOOP_TOL
    LINK_RULES JRT_FROM_TOP JT_LINK_MODES JT_LINK_DEFAULT _JT_LINK_FALLBACK
    _CX_LINK_END_OFF BOOL_OPTS DIR_OPTS zmode_defs _note _cfg_num

对外符号(主脚本再导出; 外部消费者依赖 m.guess_std_rule / m.sanitize_std_rule /
m.collect_circle_anchors / m.DEFAULT_JRT / m.Log(后者不在本模块)):
    _jt_link_values jt_mode_with_memory _cx_link_values derive_linked
    jrt_with_memory anchors_overflow stdparts_dir std_part_defaults
    guess_std_rule sanitize_std_rule _rule_usable _unusable_names
    discover_std_parts merge_std_rules merge_jrt default_params
    set_json_path_provider set_stdparts_lister _json_path load_state _name_list
    save_state merge_params resolve_dxf_path
    _place_delta _center_seen collect_circle_anchors _std_z
"""

import io
import json
import os
import time

# 以下名字由主脚本在加载后注入(见 nx_extrude_runner.py 的 _inject)。缺省值仅为
# "万一被独立 import"时的兜底; 其中 LOOP_TOL 还被 _center_seen 用作默认参数,
# 必须在定义该函数前就有值(默认参数在 def 时求值, 注入却在加载后)。
LOOP_TOL = 0.01


# ---------------------------------------------------------------------------
# 测试注入点(P0): 自测不再靠 globals() 猴补主模块符号, 统一走这两个 setter。
# ---------------------------------------------------------------------------
_json_path_provider = None
_stdparts_lister = None


def set_json_path_provider(fn):
    """替换记忆文件路径来源(fn 返回 str); 传 None 恢复真实实现。供自测隔离临时目录。"""
    global _json_path_provider
    _json_path_provider = fn


def set_stdparts_lister(fn):
    """替换标准件目录扫描来源(fn 返回文件名列表); 传 None 恢复真实实现。供自测注入固定列表。"""
    global _stdparts_lister
    _stdparts_lister = fn


# ---------------------------------------------------------------------------
# JT / CX 联动
# ---------------------------------------------------------------------------

def _jt_link_values(top, bottom, mode):
    """FLB top/bottom + 联动模式 → JT (起始, 结束)。模式无效回默认模式。"""
    off = (JT_LINK_MODES.get(mode) or JT_LINK_MODES.get(JT_LINK_DEFAULT)
           or _JT_LINK_FALLBACK["普通模式"])
    return (top + off[0], bottom + off[1])


def jt_mode_with_memory(state):
    """打开时的 JT 联动模式: 记忆有效用记忆, 否则回 config 默认。"""
    m = state.get("jt_link_mode")
    if isinstance(m, str) and m in JT_LINK_MODES:
        return m
    return JT_LINK_DEFAULT


def _cx_link_values(cx_start):
    """CX 起始(=JT 起始) → CX (起始, 结束): 起始原样, 结束=起始−偏移。"""
    return (cx_start, cx_start - _CX_LINK_END_OFF)


def derive_linked(top, bottom, jt_mode=None):
    """FLB top/bottom → 联动层参数 {code: (v1, v2)} + JRT 区间。
    jt_mode 给定时额外返回 JT 联动值(v1.37)。"""
    out = {code: fn(top, bottom) for code, fn in LINK_RULES.items()}
    out["JRT"] = (top, top - JRT_FROM_TOP)
    if jt_mode is not None:
        out["JT"] = _jt_link_values(top, bottom, jt_mode)
    return out


def jrt_with_memory(state, params):
    """打开时的加热条参数: 三几何参数恒默认; 起始/结束有记忆用记忆,
    无记忆按 FLB 当前参数联动。"""
    jrt = dict(DEFAULT_JRT)
    se = None
    if state.get("schema") == SCHEMA_VERSION:
        v = state.get("jrt_se")
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                se = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                se = None
    if se is None:
        s, e = params.get(TARGET_CODE, (0.0, 0.0))
        se = derive_linked(max(s, e), min(s, e)).get(
            "JRT", (DEFAULT_JRT["start"], DEFAULT_JRT["end"]))
    jrt["start"], jrt["end"] = se
    return jrt


def anchors_overflow(anchors, rule):
    """(纯逻辑) 数量超限或"空图层+大半径"指纹 → True。"""
    if len(anchors) > STD_MAX_ANCHORS:
        return True
    return (not rule.get("layer")) and float(rule.get("r_max", 0.0)) >= 999.0


def stdparts_dir():
    """标准件目录 = 脚本同级的 STDPARTS_DIRNAME(默认 stdparts)。

    跨版本约定: .prt 只向下不向上兼容, NX2312 母版在旧版 NX(8/10/12) 打不开。
    故交付旧版时, 用 tools\\NX向下兼容工具\\ 把母版还原成目标机版本 .prt, 直接
    放进 stdparts\\(覆盖同名), 脚本按同目录读即可——无需按版本切换目录。"""
    return os.path.join(script_dir(), STDPARTS_DIRNAME)


def std_part_defaults(fname, table=None):
    """件的默认规则(两级匹配)或 None(无默认——新件)。

    v1.30 两级匹配: 精确文件名行(带/不带 .prt)优先于关键词子串行;
    每件实测的参考点写在精确行里。table 参数供 selftest 注入测试表。
      主进胶(DP,0~8,FLB底,仅放置) 垫片(DK,0~5,FLB顶,放置+减去)
      大水口/点胶口(RZ,0~15,FLB底,仅放置) 螺丝(LS,0~5,FLB顶,放置+减去)
    恢复默认按钮仅对返回非 None 的件显示(无默认的新件点按钮=无效不报错)。
    """
    # 出厂默认表在 nx_std_config.py(注释齐全可自行编辑); 这里只是
    # 配置文件缺失时的内置兜底(内容同款)。
    if table is None and _USER_CFG is not None:
        try:
            table = [(str(k), dict(v))
                     for k, v in _USER_CFG.STD_PART_DEFAULTS]
        except Exception:
            table = None
    if not table:
        table = (
            ("主进胶", {"layer": "DP", "r_min": 0.0, "r_max": 8.0,
                      "z_mode": "FLB_BOTTOM",
                      "bool_mode": "PLACE_SUBTRACT"}),
            ("大水口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                      "z_mode": "FLB_BOTTOM"}),
            ("点胶口", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                      "z_mode": "FLB_BOTTOM"}),
            ("热咀", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                     "z_mode": "FLB_BOTTOM"}),
            ("nozzle", {"layer": "RZ", "r_min": 0.0, "r_max": 15.0,
                       "z_mode": "FLB_BOTTOM"}),
            ("螺丝", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                    "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("screw", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                     "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("ls-", {"layer": "LS", "r_min": 0.0, "r_max": 5.0,
                   "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("接线盒", {"layer": "CXK", "z_mode": "CX_TOP"}),
            ("垫片", {"layer": "DK", "r_min": 0.0, "r_max": 5.0,
                    "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
            ("washer", {"layer": "DK", "r_min": 0.0, "r_max": 5.0,
                      "z_mode": "FLB_TOP", "bool_mode": "PLACE_SUBTRACT"}),
        )
    low = fname.lower()
    stem = low[:-4] if low.endswith('.prt') else low
    for key, over in table:
        k = key.lower()
        if k == low or k == stem or k == stem + '.prt':
            r = dict(DEFAULT_STD_RULE)
            r.update(over)
            return r
    for key, over in table:
        if key.lower() in low:
            r = dict(DEFAULT_STD_RULE)
            r.update(over)
            return r
    return None


def guess_std_rule(fname):
    """按文件名猜默认规则(无命中回通用默认; ref 必填由 config 提供)。"""
    d = std_part_defaults(fname)
    return d if d is not None else dict(DEFAULT_STD_RULE)


def sanitize_std_rule(rule):
    """规则字段规范化(坏值回默认, r_min/r_max 保序)。"""
    out = dict(DEFAULT_STD_RULE)
    if not isinstance(rule, dict):
        return out
    lay = str(rule.get("layer", "") or "").upper()
    out["layer"] = lay if lay in LAYER_CODES + ["CXK"] else ""
    for k in ("r_min", "r_max", "off_x", "off_y", "off_z"):
        try:
            out[k] = float(rule.get(k, out[k]))
        except (TypeError, ValueError):
            pass
    if out["r_max"] < out["r_min"]:
        out["r_min"], out["r_max"] = out["r_max"], out["r_min"]
    if rule.get("z_mode") in [k for k, _l, _ly, _sd in zmode_defs()]:
        out["z_mode"] = rule["z_mode"]
    if rule.get("bool_mode") in [v for v, _t in BOOL_OPTS]:
        out["bool_mode"] = rule["bool_mode"]
    if rule.get("dir") in [v for v, _t in DIR_OPTS]:
        out["dir"] = rule["dir"]
    ref = rule.get("ref")
    if isinstance(ref, (list, tuple)) and len(ref) == 3:
        try:
            out["ref"] = [float(ref[0]), float(ref[1]), float(ref[2])]
        except (TypeError, ValueError):
            out["ref"] = None
    else:
        out["ref"] = None
    return out


def _rule_usable(rule):
    """(纯逻辑) 规则可用 = ref 为 3 个数字。"""
    ref = rule.get("ref") if isinstance(rule, dict) else None
    return (isinstance(ref, (list, tuple)) and len(ref) == 3
            and all(isinstance(v, float) for v in ref))


def _unusable_names(rules):
    """(纯逻辑) {文件名: 规则} → 未配置 ref 的文件名排序列表。"""
    return sorted(f for f, r in rules.items() if not _rule_usable(r))


def discover_std_parts():
    """扫描 stdparts 目录下 .prt(目录不存在则创建) → 排序文件名列表。

    (P0) 注入点: 测试可经 set_stdparts_lister() 替换本扫描。
    """
    if _stdparts_lister is not None:
        return list(_stdparts_lister())
    d = stdparts_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return []
    try:
        return sorted(n for n in os.listdir(d) if n.lower().endswith(".prt"))
    except OSError:
        return []


def merge_std_rules(state):
    """发现到的文件 × (JSON 记忆 | 文件名猜测) → {文件名: 规范化规则}。

    v1.9: JSON 带 schema:2 才读记忆(旧 JSON 的规则字段已改, 忽略防
    旧记忆覆盖新默认); 首次保存后恢复正常记忆。
    """
    if state.get("schema") != SCHEMA_VERSION:
        state = {}
    saved = state.get("std_parts") or {}
    out = {}
    for fname in discover_std_parts():
        out[fname] = sanitize_std_rule(saved.get(fname) or guess_std_rule(fname))
    return out


def merge_jrt(state):
    """JRT 参数: 每次固定默认(3.9/0.1/3.7), 不再读 JSON 记忆。

    (v1.9 教训: JSON 记忆覆盖默认值, 用户改过一次后默认值就"变了";
    start/end 由对话框 FLB 联动实时刷新, 也无需记忆。)
    """
    return dict(DEFAULT_JRT)


def default_params():
    """无记忆时的兜底参数: FLB 取 config 默认(-40/-85), 其余联动层按
    联动规则从 FLB 推导(JT 按默认模式, CX 随 JT)。"""
    out = {r[0]: (float(r[3]), float(r[4])) for r in LAYER_TABLE}
    s, e = out[TARGET_CODE]
    linked = derive_linked(max(s, e), min(s, e), jt_mode=JT_LINK_DEFAULT)
    for code, (v1, v2) in linked.items():
        if code in out:
            out[code] = (v1, v2)
    out["CX"] = _cx_link_values(linked["JT"][0])
    return out


# ---------------------------------------------------------------------------
# 参数记忆(nx_extrude_params.json)
# ---------------------------------------------------------------------------

def _json_path():
    if _json_path_provider is not None:
        return _json_path_provider()
    return os.path.join(script_dir(), "nx_extrude_params.json")


def load_state():
    p = _json_path()
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 坏记忆隔离留证(改名备份), 防止下次 save 用默认值覆盖掉现场
        if os.path.isfile(p):
            try:
                bak = "%s.bad-%s" % (p, time.strftime("%Y%m%d-%H%M%S"))
                os.replace(p, bak)
                _note("nx_extrude_params.json 损坏, 已隔离为 %s, "
                                  "本次按全新记忆处理。" % os.path.basename(bak))
            except OSError:
                pass
        return {}


def _name_list(v):
    """记忆中的文件名列表容错: list/tuple → [str]; 其余(含坏类型)→ []。"""
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return []


def save_state(dxf_path, params, std_rules=None, selected=None, jrt_se=None,
               jt_link_mode=None):
    """落盘记忆(临时文件+原子替换: 中途崩溃/断电不损原记忆)。

    jrt_se 只存加热条起始/结束两个距离(三个几何参数永不落盘,
    打开恒 3.9/0.1/3.7); 传 None 时原样写 null(=无记忆, 按 FLB 联动)。
    jt_link_mode 存 JT 联动模式(v1.37); None 写 null(=无记忆, 回 config 默认)。
    """
    try:
        p = _json_path()
        if not isinstance(jt_link_mode, str):
            # 未显式给模式 → 保留旧记忆里的模式(v1.38 修复: 选件落盘等
            # 局部保存不带 jt_link_mode, 曾把已选模式抹成 null)
            try:
                with io.open(p, encoding="utf-8") as f_old:
                    _old_mode = json.load(f_old).get("jt_link_mode")
                if isinstance(_old_mode, str):
                    jt_link_mode = _old_mode
            except Exception:
                pass
        tmp = "%s.tmp" % p
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA_VERSION,
                       "dxf_path": dxf_path, "params": params,
                       "std_parts": std_rules or {},
                       "selected": _name_list(selected),
                       "jrt_se": (list(jrt_se)
                                  if isinstance(jrt_se, (list, tuple))
                                  and len(jrt_se) == 2 else None),
                       "jt_link_mode": (jt_link_mode
                                        if isinstance(jt_link_mode, str)
                                        else None)}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as ex:
        _note("记忆保存失败(%s: %s)。" % (type(ex).__name__, ex))


def merge_params(state):
    """记忆值与默认值合并(记忆优先)。

    schema 门控(v1.35): 版本不符时界面参数(params)一并回默认——与
    config 注释"调大 CONFIG_SCHEMA_VERSION 连界面参数一起回默认"一致。
    """
    out = default_params()
    if not isinstance(state, dict) or state.get("schema") != SCHEMA_VERSION:
        return out
    raw = state.get("params")
    if not isinstance(raw, dict):
        return out                # 坏类型(列表/字符串等)按无记忆处理, 不崩
    for code, v in raw.items():
        if code in out and isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                out[code] = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                pass
    return out


def resolve_dxf_path(state):
    """DXF 路径: 记忆值优先, 否则脚本目录最新 *.dxf。"""
    p = state.get("dxf_path") or ""
    if p and os.path.isfile(p):
        return p
    try:
        cands = [os.path.join(script_dir(), n) for n in os.listdir(script_dir())
                 if n.lower().endswith(".dxf")]
        if cands:
            return max(cands, key=os.path.getmtime)
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------------------
# 放置 / 锚点 / Z 基准 纯逻辑(原夹在 §5 NX 段中间, 一并收拢到规则层)
# ---------------------------------------------------------------------------

def _place_delta(ref, flip, off):
    """(纯逻辑)放置位移: basePoint = 锚点 + 本函数返回值。

    basePoint = 锚点 − R·ref + off(R 为插入姿态矩阵):
      +Z(R=I)      → (−ref_x+ox, −ref_y+oy, −ref_z+oz)
      -Z(绕X 180°) → ref 的 y/z 分量随零件坐标系翻转反号——此前直接用
                     −ref, 翻转件对位误差 = (0, 2·ref_y, 2·ref_z)(v1.35 修复)
    """
    rx = _cfg_num(ref[0], 0.0)
    ry = _cfg_num(ref[1], 0.0)
    rz = _cfg_num(ref[2], 0.0)
    ox = _cfg_num(off[0], 0.0)
    oy = _cfg_num(off[1], 0.0)
    oz = _cfg_num(off[2], 0.0)
    if flip:
        ry, rz = -ry, -rz
    return (-rx + ox, -ry + oy, -rz + oz)


def _center_seen(grid, x, y, tol=LOOP_TOL):
    """量化网格 + 3×3 邻桶判同心: 已见返回 True, 未见登记并返回 False。

    (v1.35) 替代对 found 的 O(n²) 线性 any() 扫描——"空图层+全半径"配错
    时上万圆心的去重曾先行卡死, 护栏来不及救。
    """
    kx, ky = int(round(x / tol)), int(round(y / tol))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for px, py in grid.get((kx + dx, ky + dy), ()):
                if abs(px - x) < tol and abs(py - y) < tol:
                    return True
    grid.setdefault((kx, ky), []).append((x, y))
    return False


def collect_circle_anchors(layers, rule):
    """规则筛选圆/圆弧圆心 → [(cx, cy, r)]; 同心去重。

    v1.10: 定位图层=CXK 时改为"线中点"锚点——2D 图 CXK 层只画一条线,
    中点即放置点(接线盒规则; 半径字段对该层无意义, 忽略)。
    """
    lay = rule.get("layer") or ""
    if lay == "CXK":
        found, grid = [], {}
        for e in (layers.get("CXK") or []):
            if e.kind == "line":
                mx = (e.p1[0] + e.p2[0]) / 2.0
                my = (e.p1[1] + e.p2[1]) / 2.0
                if not _center_seen(grid, mx, my):
                    found.append((mx, my, 0.0))
        return found
    codes = [lay] if lay else LAYER_CODES
    rmin, rmax = rule["r_min"], rule["r_max"]
    found, grid = [], {}
    for code in codes:
        for e in (layers.get(code) or []):
            if e.kind in ("circle", "arc") and (rmin - 1e-9) <= e.r <= (rmax + 1e-9):
                c = e.c
                if not _center_seen(grid, c[0], c[1]):
                    found.append((c[0], c[1], e.r))
    return found


def _std_z(params, rule):
    """插入点 Z = z_mode 查 ZMODE_DEFS 选出的基准面 + off_z。

    负区间也正确(top=max, bottom=min)。查不到的 z_mode(如旧 json 的
    ABS)回 FLB 顶面。
    """
    zm = rule["z_mode"]
    for _k, _lbl, layer, side in zmode_defs():
        if _k == zm:
            s, e = params.get(layer, (0.0, 0.0))
            base = max(s, e) if side == "TOP" else min(s, e)
            return base + rule["off_z"]
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    return max(s, e) + rule["off_z"]
