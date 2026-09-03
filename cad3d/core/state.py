# -*- coding: utf-8 -*-
"""cad3d.core.state —— 参数联动推导与 JSON 记忆持久化。"""

import io
import json
import os
import time

from cad3d.core.paths import _json_path
from cad3d.core.config import _note, SCHEMA_VERSION
from cad3d.core.constants import (
    LAYER_TABLE, TARGET_CODE, LINK_RULES, JRT_FROM_TOP,
    JT_LINK_MODES, JT_LINK_DEFAULT, _JT_LINK_FALLBACK,
    _CX_LINK_END_OFF, DEFAULT_JRT
)


def _jt_link_values(top, bottom, mode):
    """FLB top/bottom + 联动模式 → JT (起始, 结束)。模式无效回默认模式。"""
    off = (JT_LINK_MODES.get(mode) or JT_LINK_MODES.get(JT_LINK_DEFAULT)
           or _JT_LINK_FALLBACK["普通模式"])
    return (top + off[0], bottom + off[1])


def jt_mode_with_memory(state):
    """打开时的 JT 联动模式: 记忆有效用记忆, 否则回 config 默认。"""
    if not isinstance(state, dict):
        return JT_LINK_DEFAULT
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
    if isinstance(state, dict) and state.get("schema") == SCHEMA_VERSION:
        v = state.get("jrt_se")
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                se = (float(v[0]), float(v[1]))
            except (TypeError, ValueError):
                se = None
    if se is None:
        p_dict = params if isinstance(params, dict) else {}
        s, e = p_dict.get(TARGET_CODE, (0.0, 0.0))
        se = derive_linked(max(s, e), min(s, e)).get(
            "JRT", (DEFAULT_JRT["start"], DEFAULT_JRT["end"]))
    jrt["start"], jrt["end"] = se
    return jrt


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
    tmp = None
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
        data = {
            "$schema_description": {
                "file_purpose": "CAD3D 自动化分层拉伸运行时参数记忆持久化文件（由程序自动维护）",
                "tips": "如遇参数错乱，可直接删除本文件，系统下次运行会自动以 nx_std_config.py 出厂配置重建",
                "fields": {
                    "schema": "记忆数据结构版本号，需与 nx_std_config.py 的 CONFIG_SCHEMA_VERSION 保持一致",
                    "dxf_path": "上次成功读取的 AutoCAD 2D 图纸 (.dxf) 绝对路径",
                    "params": "各图层的拉伸起始与结束绝对坐标 [起始, 结束] (mm)",
                    "std_parts": "各标准件的独立参数微调字典（图层、搜索半径、Z基准、布尔方式、姿态偏移）",
                    "selected": "上次在【标准件选择窗口】中勾选激活的标准件零件文件名清单",
                    "jrt_se": "加热条 (JRT) 的起止区间 [起始, 结束] (mm)",
                    "jt_link_mode": "上次选中的假体 (JT) 联动模式（如'普通模式'或'针阀模式'）"
                }
            },
            "schema": SCHEMA_VERSION,
            "dxf_path": dxf_path,
            "params": params,
            "std_parts": std_rules or {},
            "selected": _name_list(selected),
            "jrt_se": (list(jrt_se)
                       if isinstance(jrt_se, (list, tuple))
                       and len(jrt_se) == 2 else None),
            "jt_link_mode": (jt_link_mode
                             if isinstance(jt_link_mode, str)
                             else None)
        }
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        tmp = None
    except Exception as ex:
        _note("记忆保存失败(%s: %s)。" % (type(ex).__name__, ex))
    finally:
        if tmp is not None and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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


def merge_jrt(state):
    """JRT 参数: 每次固定默认(3.9/0.1/3.7), 不再读 JSON 记忆。"""
    return dict(DEFAULT_JRT)
