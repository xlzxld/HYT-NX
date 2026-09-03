# -*- coding: utf-8 -*-
"""cad3d.selftest.sample_dxf —— 自动化合成多图层测试 DXF。"""

import io


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
