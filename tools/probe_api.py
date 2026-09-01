# -*- coding: utf-8 -*-
"""查 uf.Plot/uf.Disp/uf.Modeling 的图像/STL 导出 API。"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import NXOpen  # noqa: E402
import NXOpen.UF  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
uf = NXOpen.UF.UFSession.GetUFSession()
out = []
out.append("uf.Plot: " + ", ".join(m for m in dir(uf.Plot)
                                   if not m.startswith("_")))
out.append("uf.Disp: " + ", ".join(m for m in dir(uf.Disp)
                                   if not m.startswith("_")))
out.append("uf.Modeling 导出类: " + ", ".join(
    m for m in dir(uf.Modeling) if any(k in m.lower()
                                       for k in ("export", "stl", "image"))))
out.append("session 成员(image/snap): " + ", ".join(
    m for m in dir(NXOpen.Session.GetSession())
    if any(k in m.lower() for k in ("image", "snap", "photo"))))
with io.open(os.path.join(_ROOT, "test", "exp_api.txt"),
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("API OK")
