# -*- coding: utf-8 -*-
"""cad3d.core.logging —— 日志收集与输出。"""


def _fmt_num(v):
    return ("%.4f" % float(v)).rstrip("0").rstrip(".") or "0"


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
