# -*- coding: utf-8 -*-
"""查 uf.Plot/uf.Disp/uf.Modeling 的图像/STL 导出 API。"""
import io
import sys

sys.path.insert(0, r"C:\Users\5600\Documents\Zcode2D\NX")
import NXOpen  # noqa: E402
import NXOpen.UF  # noqa: E402

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
with io.open(r"C:\Users\5600\Documents\Zcode2D\NX\test\.zcode\exp_api.txt",
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("API OK")
