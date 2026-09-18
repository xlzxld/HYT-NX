# -*- coding: utf-8 -*-
"""cad3d.modeling.nx_compat —— NXOpen 跨版本调用与对象属性封装。"""

import math

from cad3d.core.constants import SCRIPT_VERSION

MARK_ATTR = "CAD3D"
TYPE_ATTR = "CAD3D_TYPE"
# 标准件体的"锚点记录"属性: v3.3 起是 7 个数「锚点x,y,z, 记时体中心x,y,z, 角度」
#   反推(v3.5 动态锚点): 当前锚点 = 当前体中心 + (记时锚点 − 记时体中心)
#   —— 记时锚点与记时体中心构成偏移, 件被平移(挪到模具上)后锚点**跟着走**;
#   而锚点在 placed_hook(移面/回位)之后才记, 长度怎么改都不会漂。
#   旧版 4 个数「dx,dy,dz,ang」= 锚点 − 体中心 的偏移, 同口径换算(老模型兼容)。
#   ang = 该件的放置角(压线板逐板判向用; 其余件恒 0)。
#   ⚠️ 只跟平移; 旋转对位不在支持范围。
ANCHOR_ATTR = "CAD3D_ANCHOR_OFF"


def _set_expr(expr, value_str):
    """跨版本写 NXOpen.Expression 公式。

    NX2312 的 Expression 有 SetFormula(str)；NX10/12 绑定无该方法(实机端到端报
    'NXOpen.Expression' object has no attribute 'SetFormula')，改用 .RightHandSide
    =str(与本文件 Limits 各处同款, 旧版可用)。先试 SetFormula 保证 2312 零回归。"""
    try:
        expr.SetFormula(value_str)
    except Exception:
        expr.RightHandSide = value_str


def _mark_type(obj, type_str):
    """体类型标记(模具开框按类型套规则用); 失败静默跳过不影响建模。"""
    try:
        obj.SetAttribute(TYPE_ATTR, str(type_str))
    except Exception:
        pass


def _type_of(obj):
    """读体类型标记; 无标记返回空串(旧版流水线产物)。"""
    try:
        return str(obj.GetStringAttribute(TYPE_ATTR) or "")
    except Exception:
        return ""


def _anchor_of(obj):
    """读体上的锚点记录("锚点x,y,z, 记时中心x,y,z, 角度" 或旧版 "dx,dy,dz,ang");
    没有记录/读不到返回空串。"""
    try:
        return str(obj.GetStringAttribute(ANCHOR_ATTR) or "")
    except Exception:
        return ""


def _mark_curve(obj):
    try:
        obj.SetAttribute(MARK_ATTR, SCRIPT_VERSION)
    except Exception:
        pass


def _is_marked(obj):
    try:
        return bool(obj.GetStringAttribute(MARK_ATTR))
    except Exception:
        return False


def _iter(coll):
    """NX 集合迭代: for-in 优先, 失败退 GetObjects()。"""
    try:
        return list(coll)
    except TypeError:
        try:
            return list(coll.GetObjects())
        except Exception:
            return []


def _bodies_of(feat):
    for getter in ("GetBodies", "GetEntities"):
        try:
            arr = getattr(feat, getter)()
            if arr:
                return [b for b in arr]
        except Exception:
            continue
    return []


def _matrix3x3(nx, flip, ang_deg=0.0):
    """放置姿态: NX 实际施加 Rz(ang_deg)·(flip 时绕 X 180°), 元素如列。

    ang_deg=0 时与旧版逐位一致: 单位阵(+Z 插入) / diag(1,-1,-1)(-Z 插入);
    ang_deg≠0 叠加绕世界 Z 面内旋转(YXB 压线板逐板自动判向, 零件先按
    dir 翻转再旋转)。
    NX2312 实机探针定案(2026-09-09): AddComponent 对 Matrix3x3 按传入
    元素矩阵的【转置】生效——传 Rz(+θ) 元素世界得 Rz(−θ), 轴向角(0/±90/
    180)不可辨, 斜槽壁实测歪 2×倾角(1.prt 取证)。故非翻转分支按 Rz(−θ)
    元素传入使世界恰为 Rz(+ang_deg); 翻转分支矩阵对称(Rz·Rx180 自转置),
    维持原值即世界=Rz(+θ)·Rx180, 无需改。"""
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    if flip:
        vals = (ca, sa, 0.0,
                sa, -ca, 0.0,
                0.0, 0.0, -1.0)
    else:
        vals = (ca, sa, 0.0,
                -sa, ca, 0.0,
                0.0, 0.0, 1.0)
    try:
        return nx.Matrix3x3(*vals)
    except TypeError:
        m = nx.Matrix3x3()
        for name, v in zip(("Xx", "Xy", "Xz", "Yx", "Yy", "Yz", "Zx", "Zy", "Zz"), vals):
            setattr(m, name, v)
        return m
