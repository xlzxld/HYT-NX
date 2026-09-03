# -*- coding: utf-8 -*-
"""cad3d.geom.entities —— 纯 Python 2D 几何图元数据结构。"""

import math


class DXLine(object):
    __slots__ = ("p1", "p2")
    kind = "line"

    def __init__(self, p1, p2):
        self.p1, self.p2 = p1, p2


class DXArc(object):
    __slots__ = ("c", "r", "a0", "a1")     # 角度: 弧度, CCW a0→a1
    kind = "arc"

    def __init__(self, c, r, a0, a1):
        self.c, self.r, self.a0, self.a1 = c, r, a0, a1

    @property
    def p1(self):
        return (self.c[0] + self.r * math.cos(self.a0),
                self.c[1] + self.r * math.sin(self.a0))

    @property
    def p2(self):
        return (self.c[0] + self.r * math.cos(self.a1),
                self.c[1] + self.r * math.sin(self.a1))


class DXCircle(object):
    __slots__ = ("c", "r")
    kind = "circle"

    def __init__(self, c, r):
        self.c, self.r = c, r
