# -*- coding: utf-8 -*-
"""v1.29 端到端演练: 垫片规则临时加 ref(取期刊已知位置), 验证:
①日志出现"配置参考点"; ②落位与自动链完全一致(同样的已知好位置);
③老件不带 ref 时自动链照旧。"""
import io
import sys

import os as _os, sys as _sys
_sys.dont_write_bytecode = True
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))
_FIXTURES = _os.path.join(_HERE, "fixtures")
import NXOpen  # noqa: E402
import nx_extrude_runner as m  # noqa: E402

session = NXOpen.Session.GetSession()
session.Parts.NewDisplay("t_ref", NXOpen.Part.Units.Millimeters)
work_part = session.Parts.Work
out = []
PARAMS = {
    "FLB": (-40.0, -90.0), "JT": (-30.0, -100.0), "LS": (-40.0, -90.0),
    "RZ": (-77.0, -90.0), "DK": (-40.0, -43.0), "DP": (-83.2977, -90.0),
    "CX": (-30.0, -65.0),
}
# 垫片规则带 ref(期刊已知位置: 主导轴XY+库Z 的等效值)
rule = m.sanitize_std_rule(m.guess_std_rule("垫片.prt"))
rule["ref"] = [2157.282, -395.735, -315.189]
STD = {"垫片.prt": rule}

lines = []
ok, _st = m.run_pipeline(
    _os.path.join(_FIXTURES, "01.dxf"),
    PARAMS, session=session, work_part=work_part,
    log=lambda t: lines.append(t), std_rules=STD, jrt=None)
for ln in lines:
    if "垫片" in ln and ("参考点" in ln or "放置" in ln):
        out.append("REF路径: " + ln[:140])
out.append("ref路径 run=%s" % ok)

lines2 = []
ok2, _st2 = m.run_pipeline(
    _os.path.join(_FIXTURES, "01.dxf"),
    PARAMS, session=session, work_part=work_part,
    log=lambda t: lines2.append(t), std_rules=STD, jrt=None)
for ln in lines2:
    if "垫片" in ln and ("参考点" in ln or "放置" in ln):
        out.append("REF路径二轮: " + ln[:140])
out.append("ref路径二轮 run=%s" % ok2)

# 回归: 老件不带 ref(3Dtest 全家桶) 自动链应照旧
lines3 = []
ok3, _st3 = m.run_pipeline(
    _os.path.join(_FIXTURES, "3Dtest.dxf"),
    PARAMS, session=session, work_part=work_part,
    log=lambda t: lines3.append(t), std_rules={}, jrt=None)
for ln in lines3:
    if "参考点=" in ln:
        out.append("回归自动链: " + ln[:130])
out.append("回归 run=%s" % ok3)

with io.open(_os.path.join(_HERE, "v_ref.txt"),
             "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("REFDRILL OK")
