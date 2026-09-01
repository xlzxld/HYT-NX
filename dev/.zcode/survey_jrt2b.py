# -*- coding: utf-8 -*-
"""jrt2 六状态: 逐面清单 + 面片三角导出(.tri) 供本地渲染。"""
import io
import sys

sys.path.insert(0, r"C:\Users\5600\Documents\Zcode2D\NX")
import NXOpen  # noqa: E402
import NXOpen.UF  # noqa: E402

session = NXOpen.Session.GetSession()
uf = NXOpen.UF.UFSession.GetUFSession()
out = []

prt, _st = session.Parts.Open(r"C:\Users\5600\Documents\Zcode2D\test\jrt2.prt")
session.Parts.SetActiveDisplay(
    prt, NXOpen.DisplayPartOption.AllowAdditional,
    NXOpen.PartDisplayPartWorkPartOption.UseLast)
session.Parts.SetWork(prt)

rows = []
for bi, b in enumerate(prt.Bodies):
    faces = list(b.GetFaces())
    zhi = max(uf.Modeling.AskFaceData(f.Tag)[3][5] for f in faces)
    rows.append((zhi, bi, faces))
rows.sort(key=lambda t: -t[0])
names = ["A", "B", "C", "D", "E", "F"]

def facet_triangles(b):
    """体 → [(v0, v1, v2), ...] 三角片; 多种签名自适应。"""
    model = None
    errs = []
    for args in ((b.Tag,), (b.Tag, uf.Facet.AskDefaultParameters()),
                 (b.Tag, None)):
        try:
            r = uf.Facet.FacetSolid(*args)
            model = r[0] if isinstance(r, tuple) else r
            break
        except Exception as ex:
            errs.append(repr(ex)[:80])
    if model is None:
        return None, errs
    tris = []
    try:
        n = uf.Facet.AskNFacetsInModel(model)
    except Exception as ex:
        return None, errs + [repr(ex)[:80]]
    ftag = 0
    seen = 0
    dbg = []
    while seen < n:
        try:
            ftag = uf.Facet.CycleFacets(model, ftag)
        except Exception as ex:
            dbg.append("cycle异常@%d %r" % (seen, ex))
            break
        if not ftag:
            dbg.append("cycle归零@%d" % seen)
            break
        seen += 1
        if seen == 1:
            dbg.append("model=%r n=%r 首面=%r" % (model, n, ftag))
        try:
            verts = uf.Facet.AskVerticesOfFacet(model, ftag)
        except Exception:
            continue
        if verts is None:
            continue
        if isinstance(verts, tuple):
            verts = verts[0] if len(verts) else []
        pts = [(float(v[0]), float(v[1]), float(v[2])) for v in verts]
        for i in range(1, len(pts) - 1):
            tris.append((pts[0], pts[i], pts[i + 1]))
    if not tris:
        errs.append(";".join(dbg) or "无调试")
    return tris, errs

for idx, (zhi, bi, faces) in enumerate(rows):
    nm = names[idx] if idx < len(names) else "G%d" % idx
    lines = []
    for f in faces:
        d = uf.Modeling.AskFaceData(f.Tag)
        bb = d[3]
        lines.append("型%d R%6.2f c=(%7.1f,%7.1f,%7.2f) 尺寸 %6.1f %6.1f %6.1f"
                     % (int(d[0]), float(d[4]), (bb[0] + bb[3]) / 2,
                        (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2,
                        bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]))
    with io.open(r"C:\Users\5600\Documents\Zcode2D\NX\test\.zcode\j2_%s.txt"
                 % nm, "w", encoding="utf-8") as fo:
        fo.write("\n".join(lines))
    tris, errs = facet_triangles(list(prt.Bodies)[bi])
    if tris is None:
        out.append("%s: 面片失败 %s" % (nm, errs))
        continue
    with io.open(r"C:\Users\5600\Documents\Zcode2D\NX\test\.zcode\j2_%s.tri"
                 % nm, "w", encoding="utf-8") as fo:
        for t in tris:
            for v in t:
                fo.write("%.3f %.3f %.3f\n" % (v[0], v[1], v[2]))
    out.append("%s: 三角形 %d %s" % (nm, len(tris), ";".join(errs)[:200]))

with io.open(r"C:\Users\5600\Documents\Zcode2D\NX\test\.zcode\jrt2_faces.txt",
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("J2F OK")
