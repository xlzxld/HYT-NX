# -*- coding: utf-8 -*-
"""v1.26 验收: 01.dxf 单跑 + 逐条体检 + 结构签名 + 存盘(全新文件名绕 NX 日志缓存)。"""
import io
import sys

import os as _os, sys as _sys
_sys.dont_write_bytecode = True
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))
_FIXTURES = _os.path.join(_HERE, "fixtures")
import NXOpen  # noqa: E402
import NXOpen.UF  # noqa: E402
import nx_extrude_runner as m  # noqa: E402

session = NXOpen.Session.GetSession()
session.Parts.NewDisplay("t_01x", NXOpen.Part.Units.Millimeters)
work_part = session.Parts.Work
uf = NXOpen.UF.UFSession.GetUFSession()
out = []
PARAMS = {
    "FLB": (-40.0, -90.0), "JT": (-30.0, -100.0), "LS": (-40.0, -90.0),
    "RZ": (-77.0, -90.0), "DK": (-40.0, -43.0), "DP": (-83.2977, -90.0),
    "CX": (-30.0, -65.0),
}
ok, stats = m.run_pipeline(
    _os.path.join(_FIXTURES, "01.dxf"),
    PARAMS, session=session, work_part=work_part, log=lambda t: None,
    std_rules={}, jrt=None)
out.append("run=%s JRT profiles=%s" % (ok, stats.get("JRT", {}).get("profiles")))
n_bad = 0
for b in work_part.Bodies:
    if not m._is_marked(b):
        continue
    faces = list(b.GetFaces())
    zs = [uf.Modeling.AskFaceData(fc.Tag)[3] for fc in faces]
    z0 = min(d[2] for d in zs)
    z1 = max(d[5] for d in zs)
    if not (4 < z1 - z0 < 11):
        continue
    rows = m._body_face_rows(uf, b)
    okh, why = m._faces_healthy(rows)
    r39 = sum(1 for t, r, z in rows if abs(r - 3.9) < 0.05)
    r37 = sum(1 for t, r, z in rows if abs(r - 3.7) < 0.05)
    smalls = []
    for fc in faces:
        d = uf.Modeling.AskFaceData(fc.Tag)
        bb = d[3]
        if int(d[0]) == 22 and (bb[3] - bb[0]) <= 3 and (bb[4] - bb[1]) <= 3:
            smalls.append("(%.1f,%.1f)" % ((bb[0] + bb[3]) / 2,
                                           (bb[1] + bb[4]) / 2))
    if not okh:
        n_bad += 1
    out.append("条: 面%d R3.9=%d R3.7=%d 碎片=%s 出线口小面%d %s"
               % (len(faces), r39, r37, why if not okh else "无", len(smalls),
                  smalls))
out.append("异形条=%d (期望0)" % n_bad)
work_part.SaveAs(_os.path.join(_HERE, "01_result_v126.prt"))
out.append("已存 01_result_v126.prt")
with io.open(_os.path.join(_HERE, "v01x.txt"),
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("T01X OK")
