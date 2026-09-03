# -*- coding: utf-8 -*-
"""cad3d.core.constants —— 参数表与常量定义。"""

from cad3d.core.config import (
    _cfg, _cfg_int, _cfg_num, _note, _USER_CFG,
    _JRT_BLEND_R, _JRT_R_STEP, _JRT_R_MIN, SCHEMA_VERSION
)

SCRIPT_VERSION = "1.40"
FEATURE_PREFIX = "CAD3D_"          # 本脚本产出的特征名前缀(清理/重建依据)
COMP_PREFIX    = FEATURE_PREFIX + "C_"   # 标准件组件实例名前缀
LOOP_TOL       = 0.01              # 环链端点连接容差(mm)
CHAIN_TOL      = 0.01              # NX Section 链接容差(mm)

# (图层码, 中文说明, 布尔角色) + 图层号/默认距离来自 config(v1.33)
# NX 图层号避开 1(默认层): FLB=NX_LAYER_START 起, JT/LS/RZ/DK/DP/CX 依次+1
_LAYER_DEFS = [
    ("FLB", "分流板", "target"),
    ("JT",  "假体",   "none"),
    ("LS",  "螺丝孔", "subtract"),
    ("RZ",  "热咀孔", "subtract"),
    ("DK",  "点孔",   "subtract"),
    ("DP",  "垫片",   "subtract"),
    ("CX",  "出线槽", "none"),
]
_NX_LAYER_START = _cfg_int("NX_LAYER_START", 11)
_LAYER_DISTS = _cfg("LAYER_START_DEFAULTS", {})
if not isinstance(_LAYER_DISTS, dict):
    _LAYER_DISTS = {}
LAYER_TABLE = []
for _i, (_c, _zh, _role) in enumerate(_LAYER_DEFS):
    _d = _LAYER_DISTS.get(_c, (0.0, 35.0))
    if not isinstance(_d, (list, tuple)) or len(_d) != 2:
        _d = (0.0, 35.0)                 # 距离写成单数字/坏类型 → 回默认
    LAYER_TABLE.append((_c, _zh, _NX_LAYER_START + _i,
                        _cfg_num(_d[0], 0.0), _cfg_num(_d[1], 35.0), _role))
LAYER_CODES   = [r[0] for r in LAYER_TABLE]
# 参考图层: 只导入曲线作手工建模参照, 不参与拉伸。JRT 固定 18 号便于记忆;
# 其余 DXF 图层(LD/0/任意)按名排序从 19 起动态分配(保留区上限 70)。
REF_LAYER_TABLE = [("JRT", "加热条(参考)", _cfg_int("NX_LAYER_JRT", 18))]
DYNAMIC_START  = _cfg_int("NX_LAYER_DYNAMIC_START", 19)  # 动态图层起始号
MANAGED_MIN    = _NX_LAYER_START                      # 管理区下界
MANAGED_MAX    = _cfg_int("NX_LAYER_MAX", 70)         # 上界(每轮重建, 勿放自有图形)
if MANAGED_MAX < MANAGED_MIN:      # 交叉校验: 配反了旧曲线迁移匹配会静默失效
    _note("NX_LAYER_MAX(%d) 小于 NX_LAYER_START(%d), 已按 %d 处理。"
          % (MANAGED_MAX, MANAGED_MIN, MANAGED_MIN))
    MANAGED_MAX = MANAGED_MIN


def assign_layers(layer_names):
    """DXF 图层名 → NX 图层号: 表内静态号 + 其余按名排序动态分配(19~70)。"""
    mapping = {r[0]: r[2] for r in LAYER_TABLE}
    mapping.update({r[0]: r[2] for r in REF_LAYER_TABLE})
    used = set(mapping.values())
    nxt = DYNAMIC_START
    for name in sorted(n for n in layer_names if n not in mapping):
        while nxt in used:
            nxt += 1
        if nxt > MANAGED_MAX:
            break
        mapping[name] = nxt
        used.add(nxt)
    return mapping


TARGET_CODE = "FLB"                       # 布尔减目标图层

# 对话框分组: (组id, 组标题, [图层码...]) — 按布尔规则分组
DIALOG_GROUPS = [
    ("grp_flb",   "FLB 分流板（基准体；改动两项后 LS/RZ/DK/DP/JRT 自动联动）", ["FLB"]),
    ("grp_plain", "普通拉伸图层（JT 随 FLB 联动；起始=结束=0 则跳过）", ["JT", "CX"]),
    ("grp_sub",   "拉伸并从 FLB 减去（随 FLB 联动，可单独改）", ["LS", "RZ", "DK", "DP"]),
]

# FLB 联动规则: FLB 两值变动时按此刷新下列层(对话框 update_cb 实时联动,
# 联动后各层仍可单独修改)。以 top=max(s,e)/bottom=min(s,e) 为基:
_LINK_OFFSETS_RAW = _cfg("LINK_OFFSETS", {})
if not isinstance(_LINK_OFFSETS_RAW, dict):
    _LINK_OFFSETS_RAW = {}             # 写成非 dict → 回默认, 不崩
_LINK_OFFSETS = {_k: _cfg_num(_LINK_OFFSETS_RAW.get(_k, _d), _d)
                 for _k, _d in (("RZ", 13.0), ("DK", 3.0), ("DP", 6.7023))}
LINK_RULES = {
    "LS":  lambda top, bottom: (top, bottom),            # 与 FLB 相同
    "RZ":  lambda top, bottom: (bottom + _LINK_OFFSETS["RZ"], bottom),
    "DK":  lambda top, bottom: (top, top - _LINK_OFFSETS["DK"]),
    "DP":  lambda top, bottom: (bottom + _LINK_OFFSETS["DP"], bottom),
}
JRT_FROM_TOP = _cfg_num(_cfg("JRT_INTRUSION_DEFAULT", 7.5), 7.5)

# JT 联动模式(v1.37): config JT_LINK_MODES 提供{模式名: (起偏移, 止偏移)},
# JT 起 = FLB top + 起偏移, JT 止 = FLB bottom + 止偏移; 缺失/坏行回内置。
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

# CX 联动(v1.38): CX 起始恒=JT 起始; CX 结束 = CX 起始 − 偏移(槽深固定, 随自身
# 顶面走; 不再跟 JT 结束——JT 结束会随联动模式漂移, 不适合作槽底基准)。
# config CX_LINK_END_OFFSET 可改, 默认 35; CX 起始 -30 → 结束 -65。
_CX_LINK_END_OFF = _cfg_num(_cfg("CX_LINK_END_OFFSET", 35.0), 35.0)

# 标准件规则
STDPARTS_DIRNAME = str(_cfg("STDPARTS_DIRNAME", "stdparts"))

# 标准件规则默认值(v1.30: ref 必填, 用户在 config 按文件名填写;
# 无 ref → _rule_usable=False → 该件跳过不用并提示)
DEFAULT_STD_RULE = {"layer": "", "r_min": 0.0, "r_max": 9999.0,
                    "z_mode": "FLB_TOP",
                    "bool_mode": "PLACE", "dir": "+Z",
                    "off_x": 0.0, "off_y": 0.0, "off_z": 0.0,
                    "ref": None}

# 加热条(JRT)参数默认值(三几何参数恒此值不进记忆; 起始/结束随 FLB 联动)
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

# Z 基准选项表(v1.32): 由 config 的 ZMODE_DEFS 生成(用户可自行新增
# 基准模式, 加一行即生效); config 缺失/缺键/行格式坏 → 兜底内置三行。
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
            continue                   # 单行格式坏 → 跳过该行
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

# JRT 对话框字段单一数据源: (key, 中文标签)
JRT_FIELDS = [
    ("start", "起始距离"),
    ("end", "结束距离"),
    ("blend_r", "边倒圆R"),
    ("r_step", "R降级步长"),
    ("r_min", "边倒圆R下限"),
]

# 单件最大放置数量护栏(nx_std_config.STD_MAX_ANCHORS 可调; 非法回默认)
STD_MAX_ANCHORS = (_cfg_int("STD_MAX_ANCHORS", 200))
