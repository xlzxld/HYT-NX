# -*- coding: utf-8 -*-
"""cad3d.core.constants —— 工程参数表、常量与全局规则加载。"""

from cad3d.core.config import (
    _cfg, _cfg_int, _cfg_num, _note, _USER_CFG,
    _JRT_BLEND_R, _JRT_R_STEP, _JRT_R_MIN, SCHEMA_VERSION
)

# 脚本与系统版本标识
SCRIPT_VERSION = "2.2"

# 命名空间前缀配置（支持在 nx_std_config.py 中自定义）
FEATURE_PREFIX = str(_cfg("FEATURE_PREFIX", "CAD3D_"))
COMP_PREFIX    = str(_cfg("COMP_PREFIX", FEATURE_PREFIX + "C_"))

# 几何算法容差配置 (mm)
LOOP_TOL  = _cfg_num(_cfg("LOOP_TOL", 0.01), 0.01)     # 2D 轮廓链闭合端点容差
CHAIN_TOL = _cfg_num(_cfg("CHAIN_TOL", 0.01), 0.01)   # NX 截面链接曲线容差

# 核心建模图层定义与属性映射
_DEFAULT_LAYER_DEFS = [
    ("FLB", "分流板", "target"),
    ("JT",  "假体",   "none"),
    ("LS",  "螺丝孔", "subtract"),
    ("RZ",  "热咀孔", "subtract"),
    ("DK",  "点孔",   "subtract"),
    ("DP",  "垫片",   "subtract"),
    ("CX",  "出线槽", "none"),
]
_RAW_LAYER_DEFS = _cfg("LAYER_DEFS", _DEFAULT_LAYER_DEFS)
_LAYER_DEFS = []
if isinstance(_RAW_LAYER_DEFS, (list, tuple)):
    for _row in _RAW_LAYER_DEFS:
        if isinstance(_row, (list, tuple)) and len(_row) == 3:
            _LAYER_DEFS.append((str(_row[0]), str(_row[1]), str(_row[2])))
if not _LAYER_DEFS:
    _LAYER_DEFS = list(_DEFAULT_LAYER_DEFS)
LAYER_DEFS = _LAYER_DEFS

_NX_LAYER_START = _cfg_int("NX_LAYER_START", 101)
_LAYER_DISTS    = _cfg("LAYER_START_DEFAULTS", {})
if not isinstance(_LAYER_DISTS, dict):
    _LAYER_DISTS = {}

# 构建分层参数综合表：[(图层代码, 中文名称, NX图层号, 起始默认值, 结束默认值, 布尔角色)]
LAYER_TABLE = []
for _i, (_c, _zh, _role) in enumerate(_LAYER_DEFS):
    _d = _LAYER_DISTS.get(_c, (0.0, 35.0))
    if not isinstance(_d, (list, tuple)) or len(_d) != 2:
        _d = (0.0, 35.0)
    LAYER_TABLE.append((_c, _zh, _NX_LAYER_START + _i,
                        _cfg_num(_d[0], 0.0), _cfg_num(_d[1], 35.0), _role))
LAYER_CODES = [r[0] for r in LAYER_TABLE]

# 参考图层与保留区映射（默认高位图层区间 101 ~ 170）
REF_LAYER_TABLE = [("JRT", "加热条(参考)", _cfg_int("NX_LAYER_JRT", 118))]
DYNAMIC_START   = _cfg_int("NX_LAYER_DYNAMIC_START", 119)
MANAGED_MIN     = _NX_LAYER_START
MANAGED_MAX     = _cfg_int("NX_LAYER_MAX", 170)
if MANAGED_MAX < MANAGED_MIN:
    _note("NX_LAYER_MAX(%d) 小于 NX_LAYER_START(%d), 已按 %d 处理。"
          % (MANAGED_MAX, MANAGED_MIN, MANAGED_MIN))
    MANAGED_MAX = MANAGED_MIN


def assign_layers(layer_names, work_part=None, log=None):
    """根据图纸中扫描出的图层名分配 NX 实际图层号。

    智能冲突避让特性：
      - 若未传入 work_part（离线自测），直接采用高位预设图层（默认 101~118）；
      - 若传入 work_part，自动检测目标图层是否已有用户自有图形占用；
      - 若发生占用冲突，自动向后滑动寻找连续干净的空闲图层，确保 100% 零混层！
    """
    occupied = set()
    if work_part is not None:
        for coll_name in ("Curves", "Bodies", "Points", "Sketches"):
            coll = getattr(work_part, coll_name, None)
            if coll is not None:
                try:
                    for obj in coll:
                        try:
                            occupied.add(int(obj.Layer))
                        except Exception:
                            pass
                except Exception:
                    pass

    base_start = _NX_LAYER_START
    core_count = len(LAYER_TABLE)
    jrt_rel = _cfg_int("NX_LAYER_JRT", 118) - _NX_LAYER_START
    dyn_rel = _cfg_int("NX_LAYER_DYNAMIC_START", 119) - _NX_LAYER_START

    conflict = False
    if occupied:
        needed = {base_start + i for i in range(core_count)} | {base_start + jrt_rel}
        if any(ly in occupied for ly in needed):
            conflict = True

    if conflict:
        # 在 [base_start .. 240] 寻找完全不与用户图形冲突的空闲区间
        cand = base_start + 10
        found = False
        while cand <= 240:
            cand_needed = {cand + i for i in range(core_count)} | {cand + jrt_rel}
            if not any(ly in occupied for ly in cand_needed):
                found = True
                break
            cand += 10
        if not found:
            cand = base_start + 1
            while cand <= 245:
                cand_needed = {cand + i for i in range(core_count)} | {cand + jrt_rel}
                if not any(ly in occupied for ly in cand_needed):
                    found = True
                    break
                cand += 1
        if found:
            if log is not None:
                log("【图层分配】检测到图层 %s 已有用户自有图形，已启动智能避让，本次自动平移至空闲图层 %d~%d。"
                    % (sorted(needed & occupied), cand, cand + core_count - 1))
            base_start = cand

    mapping = {}
    for i, r in enumerate(LAYER_TABLE):
        mapping[r[0]] = base_start + i
    mapping["JRT"] = base_start + jrt_rel

    used = set(mapping.values()) | occupied
    nxt = base_start + dyn_rel
    for name in sorted(n for n in layer_names if n not in mapping):
        while nxt in used or nxt in occupied:
            nxt += 1
        if nxt > 256:
            break
        mapping[name] = nxt
        used.add(nxt)
    return mapping


# 布尔减目标基准图层代码
TARGET_CODE = str(_cfg("TARGET_CODE", "FLB"))

# 对话框拉伸参数分组定义
_DEFAULT_DIALOG_GROUPS = [
    ("grp_flb",   "FLB 分流板（基准体；改动两项后 LS/RZ/DK/DP/JRT 自动联动）", ["FLB"]),
    ("grp_plain", "普通拉伸图层（JT 随 FLB 联动；起始=结束=0 则跳过）", ["JT", "CX"]),
    ("grp_sub",   "拉伸并从 FLB 减去（随 FLB 联动，可单独改）", ["LS", "RZ", "DK", "DP"]),
]
_RAW_DIALOG_GROUPS = _cfg("DIALOG_GROUPS", _DEFAULT_DIALOG_GROUPS)
DIALOG_GROUPS = []
if isinstance(_RAW_DIALOG_GROUPS, (list, tuple)):
    for _g in _RAW_DIALOG_GROUPS:
        if isinstance(_g, (list, tuple)) and len(_g) == 3:
            DIALOG_GROUPS.append((str(_g[0]), str(_g[1]), list(_g[2])))
if not DIALOG_GROUPS:
    DIALOG_GROUPS = list(_DEFAULT_DIALOG_GROUPS)

# FLB 尺寸联动规则与推导偏移
_LINK_OFFSETS_RAW = _cfg("LINK_OFFSETS", {})
if not isinstance(_LINK_OFFSETS_RAW, dict):
    _LINK_OFFSETS_RAW = {}
_LINK_OFFSETS = {_k: _cfg_num(_LINK_OFFSETS_RAW.get(_k, _d), _d)
                 for _k, _d in (("RZ", 13.0), ("DK", 3.0), ("DP", 6.7023))}
LINK_RULES = {
    "LS":  lambda top, bottom: (top, bottom),
    "RZ":  lambda top, bottom: (bottom + _LINK_OFFSETS["RZ"], bottom),
    "DK":  lambda top, bottom: (top, top - _LINK_OFFSETS["DK"]),
    "DP":  lambda top, bottom: (bottom + _LINK_OFFSETS["DP"], bottom),
}
JRT_FROM_TOP = _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)

# JT 假体联动多模式配置
_JT_LINK_FALLBACK = {"普通模式": (10.0, -15.0), "针阀模式": (15.0, -15.0)}
JT_LINK_MODES = dict(_JT_LINK_FALLBACK)
_JT_RAW = _cfg("JT_LINK_MODES", None)
if isinstance(_JT_RAW, dict) and _JT_RAW:
    _jt = {}
    for _k, _v in _JT_RAW.items():
        try:
            _a, _b = float(_v[0]), float(_v[1])
        except Exception:
            continue
        if _a == _a and _b == _b:
            _jt[str(_k)] = (_a, _b)
    if _jt:
        JT_LINK_MODES = _jt
    else:
        _note("JT_LINK_MODES 无有效行, 回退内置两种模式。")
JT_LINK_DEFAULT = str(_cfg("JT_LINK_DEFAULT", "普通模式"))
if JT_LINK_DEFAULT not in JT_LINK_MODES:
    JT_LINK_DEFAULT = next(iter(JT_LINK_MODES))
    _note("JT_LINK_DEFAULT 模式名无效, 回退 %s。" % JT_LINK_DEFAULT)
JT_LINK_OPTS = [(k, k) for k in JT_LINK_MODES]

# CX 出线槽联动槽深固定偏移量
_CX_LINK_END_OFF = _cfg_num(_cfg("CX_LINK_END_OFFSET", 35.0), 35.0)

# 标准件目录名称配置
STDPARTS_DIRNAME = str(_cfg("STDPARTS_DIRNAME", "stdparts"))

# 标准件规则兜底回退定义
DEFAULT_STD_RULE = {
    "layer": "", "r_min": 0.0, "r_max": 9999.0,
    "z_mode": "FLB_TOP", "bool_mode": "PLACE", "dir": "+Z",
    "off_x": 0.0, "off_y": 0.0, "off_z": 0.0,
    "ref": None
}
_CFG_STD_RULE = _cfg("DEFAULT_STD_RULE", None)
if isinstance(_CFG_STD_RULE, dict):
    DEFAULT_STD_RULE.update(_CFG_STD_RULE)

# 加热条 (JRT) 工艺默认值
DEFAULT_JRT = {
    "start": 0.0, "end": -7.5,
    "blend_r": _JRT_BLEND_R,
    "r_step": _JRT_R_STEP,
    "r_min": _JRT_R_MIN,
    "offset": _cfg_num(_cfg("JRT_OFFSET", 5.0), 5.0),
    "draft": _cfg_num(_cfg("JRT_DRAFT", 2.0), 2.0),
    "color_strip": _cfg_int("JRT_COLOR_STRIP", 186),
    "color_model": _cfg_int("JRT_COLOR_MODEL", 78),
    "translucency": _cfg_int("JRT_TRANSLUCENCY", 50),
}

# Z 基准高度选项表
_ZMODE_FALLBACK = [("FLB_TOP", "FLB顶面", "FLB", "TOP"),
                   ("FLB_BOTTOM", "FLB底面", "FLB", "BOTTOM"),
                   ("CX_TOP", "CX顶值", "CX", "TOP")]
_ZMODE_DEFS = list(_ZMODE_FALLBACK)
if _USER_CFG is not None:
    _zm = []
    for _row in (getattr(_USER_CFG, "ZMODE_DEFS", None) or []):
        try:
            _k, _lbl, _ly, _sd = _row
            _zm.append((str(_k), str(_lbl), str(_ly), str(_sd)))
        except (TypeError, ValueError):
            continue
    if _zm:
        _ZMODE_DEFS = _zm
    else:
        _note("ZMODE_DEFS 为空或无有效行, 回退内置三种基准。")
ZMODE_OPTS     = [(k, lbl + "+偏移") for k, lbl, _ly, _sd in _ZMODE_DEFS]
BOOL_OPTS      = [("PLACE", "仅放置"), ("PLACE_SUBTRACT", "放置+减去"),
                  ("SUBTRACT", "仅减去(隐藏件)"), ("UNITE", "合并进FLB")]
DIR_OPTS       = [("+Z", "+Z插入"), ("-Z", "-Z翻转")]
LAYER_SEL_OPTS = ([("", "全部图层")]
                  + [(c, c) for c in LAYER_CODES]
                  + [("CXK", "CXK(接线盒线)")])

# JRT 参数对话框字段单一数据源
JRT_FIELDS = [
    ("start", "起始距离"),
    ("end", "结束距离"),
    ("blend_r", "边倒圆R"),
    ("r_step", "R降级步长"),
    ("r_min", "边倒圆R下限"),
]

# 单件最大放置数量护栏
STD_MAX_ANCHORS = _cfg_int("STD_MAX_ANCHORS", 200)
