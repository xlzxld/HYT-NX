# -*- coding: utf-8 -*-
"""cad3d.modeling.std_rules —— 标准件规则匹配、规范化与发现。"""

import os
from cad3d.core.paths import stdparts_dir
from cad3d.core.config import _USER_CFG, SCHEMA_VERSION
from cad3d.core.constants import (
    DEFAULT_STD_RULE, LAYER_CODES, _ZMODE_DEFS, BOOL_OPTS, DIR_OPTS,
    TARGET_CODE, STD_MAX_ANCHORS
)


def _std_z(params, rule):
    """插入点 Z = z_mode 查 ZMODE_DEFS 选出的基准面 + off_z。

    负区间也正确(top=max, bottom=min)。查不到的 z_mode(如旧 json 的
    ABS)回 FLB 顶面。
    """
    params = params if isinstance(params, dict) else {}
    rule = rule if isinstance(rule, dict) else {}
    zm = rule.get("z_mode")
    try:
        off_z = float(rule.get("off_z", 0.0))
    except (TypeError, ValueError):
        off_z = 0.0
    for _k, _lbl, layer, side in _ZMODE_DEFS:
        if _k == zm:
            s, e = params.get(layer, (0.0, 0.0))
            base = max(s, e) if side == "TOP" else min(s, e)
            return base + off_z
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    return max(s, e) + off_z


def std_part_defaults(fname, table=None):
    """件的默认规则(两级匹配)或 None(无默认——新件)。

    v1.30 两级匹配: 精确文件名行(带/不带 .prt)优先于关键词子串行;
    每件实测的参考点写在精确行里。table 参数供 selftest 注入测试表。
      主进胶(DP,0~8,FLB底,仅放置) 垫片(DK,0~5,FLB顶,放置+减去)
      大水口/点胶口(RZ,0~15,FLB底,仅放置) 螺丝(LS,0~5,FLB顶,放置+减去)
    恢复默认按钮仅对返回非 None 的件显示(无默认的新件点按钮=无效不报错)。
    """
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
    if rule.get("z_mode") in [k for k, _l, _ly, _sd in _ZMODE_DEFS]:
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
            and all(isinstance(v, (int, float)) for v in ref))


def _unusable_names(rules):
    """(纯逻辑) {文件名: 规则} → 未配置 ref 的文件名排序列表。"""
    return sorted(f for f, r in rules.items() if not _rule_usable(r))


def discover_std_parts():
    """扫描 stdparts 目录下 .prt(目录不存在则创建) → 排序文件名列表。"""
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


def anchors_overflow(anchors, rule):
    """(纯逻辑) 数量超限或"空图层+大半径"指纹 → True。"""
    if len(anchors) > STD_MAX_ANCHORS:
        return True
    return (not rule.get("layer")) and float(rule.get("r_max", 0.0)) >= 999.0
