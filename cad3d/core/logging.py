# -*- coding: utf-8 -*-
"""cad3d.core.logging —— 日志收集与输出。"""


def _fmt_num(v):
    # -0.0 归一成 "0" (曾输出 "-0", NX 表达式能吃但显示怪);
    # 4 位小数量化口径, 量级远小于建模精度
    _f = float(v)
    if _f == 0.0:
        return "0"
    return ("%.4f" % _f).rstrip("0").rstrip(".") or "0"


class Log(object):
    """日志收集器: 逐行进 ListingWindow(NX 内)并缓存供报告。"""
    def __init__(self, session=None):
        self.lines = []
        self.session = session
        if session is not None:
            try:
                session.ListingWindow.Open()
            except Exception:
                pass

    def __call__(self, msg):
        self.lines.append(msg)
        if self.session is not None:
            try:
                self.session.ListingWindow.WriteLine(msg)
            except Exception:
                pass
