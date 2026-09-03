# -*- coding: utf-8 -*-
"""cad3d.modeling.nx_compat —— NXOpen 跨版本调用与对象属性封装。"""

from cad3d.core.constants import SCRIPT_VERSION

MARK_ATTR = "CAD3D"


def _set_expr(expr, value_str):
    """跨版本写 NXOpen.Expression 公式。

    NX2312 的 Expression 有 SetFormula(str)；NX10/12 绑定无该方法(实机端到端报
    'NXOpen.Expression' object has no attribute 'SetFormula')，改用 .RightHandSide
    =str(与本文件 Limits 各处同款, 旧版可用)。先试 SetFormula 保证 2312 零回归。"""
    try:
        expr.SetFormula(value_str)
    except Exception:
        expr.RightHandSide = value_str


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


def _matrix3x3(nx, flip):
    """放置姿态: 单位阵(+Z 插入) 或绕 X 180°(-Z 插入)。"""
    vals = ((1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0) if flip
            else (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    try:
        return nx.Matrix3x3(*vals)
    except TypeError:
        m = nx.Matrix3x3()
        for name, v in zip(("Xx", "Xy", "Xz", "Yx", "Yy", "Yz", "Zx", "Zy", "Zz"), vals):
            setattr(m, name, v)
        return m
