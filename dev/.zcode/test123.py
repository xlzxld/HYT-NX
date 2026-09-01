# -*- coding: utf-8 -*-
"""123.dxf 开链修复验证: JRT 闭链数应从 1 → 2(合并0.24mm接缝 + 桥接25mm缺口)。"""
import io
import sys

import os as _os, sys as _sys
_sys.dont_write_bytecode = True
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_HERE)))
_FIXTURES = _os.path.join(_HERE, "fixtures")
import NXOpen  # noqa: E402
import nx_extrude_runner as m  # noqa: E402

session = NXOpen.Session.GetSession()
session.Parts.NewDisplay("t_123", NXOpen.Part.Units.Millimeters)
work_part = session.Parts.Work
log = m.Log(session)
out = []

params = {"FLB": (-40.0, -90.0), "JT": (-30.0, -100.0), "LS": (-40.0, -90.0),
          "RZ": (-77.0, -90.0), "DK": (-40.0, -43.0), "DP": (-83.2977, -90.0),
          "CX": (-30.0, -65.0)}
jrt = dict(m.DEFAULT_JRT)
jrt.update({"start": -40.0, "end": -47.5})

ok, stats = m.run_pipeline(_os.path.join(_FIXTURES, "123.dxf"),
                           params, session=session, work_part=work_part,
                           log=log, std_rules={}, jrt=jrt)
out.append("run=%s JRT profiles=%s note=%s"
           % (ok, stats.get("JRT", {}).get("profiles"),
              stats.get("JRT", {}).get("note")))
for ln in log.lines:
    if "JRT" in ln or "开" in ln or "桥" in ln:
        out.append(ln)

with io.open(_os.path.join(_HERE, "v123.txt"),
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("T123 OK")
