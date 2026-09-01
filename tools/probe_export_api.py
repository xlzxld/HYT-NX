# -*- coding: utf-8 -*-
"""单件实验(正规工厂): X_T(Ps270Nx100=NX10) + STEP(AP214) 导出。"""
import io
import os
import traceback
import NXOpen

OUT = r"C:\Users\5600\Documents\ZDH\NX\dev\.zcode\probe_export_result.txt"
SRC = r"C:\Users\5600\Documents\ZDH\NX\stdparts\垫片.prt"
DST_DIR = os.path.join(os.environ.get("TEMP", "."), "cad3d_xtest")
lines = []
os.makedirs(DST_DIR, exist_ok=True)

s = NXOpen.Session.GetSession()
nx = NXOpen
dm = s.DexManager

lines.append("StepCreatorExportFromOption 成员: %s" % [
    m for m in dir(nx.StepCreatorExportFromOption)
    if not m.startswith("_") and not callable(getattr(
        nx.StepCreatorExportFromOption, m, None))])

# ---------- 1. Parasolid X_T (NX10 = Ps270Nx100) ----------
x_t = os.path.join(DST_DIR, "垫片.x_t")
try:
    pe = dm.CreateParasolidExporter()
    pe.ExportFromOption = nx.ParasolidExporterExportFromOption.ExistingPart
    pe.InputFile = SRC
    pe.OutputFile = x_t
    pe.ParasolidVersionOption = \
        nx.ParasolidExporterParasolidVersionOption.Ps270Nx100
    n = pe.Commit()
    lines.append("X_T Commit=%r 存在=%s 大小=%s"
                 % (n, os.path.isfile(x_t),
                    os.path.getsize(x_t) if os.path.isfile(x_t) else -1))
    pe.Destroy()
    with open(x_t, "rb") as f:
        lines.append("X_T 文件头: %r" % f.read(100))
except Exception:
    lines.append("X_T: 失败\n%s" % traceback.format_exc())

# ---------- 2. STEP AP214 ----------
stp = os.path.join(DST_DIR, "垫片.stp")
try:
    sc = dm.CreateStepCreator()
    sc.ExportFromOption = nx.StepCreatorExportFromOption.ExistingPart
    sc.InputFile = SRC
    sc.OutputFile = stp
    sc.ExportAsOption = nx.StepCreatorExportAsOption.Ap214
    n = sc.Commit()
    sc.Destroy()
    lines.append("STP Commit=%r 存在=%s 大小=%s"
                 % (n, os.path.isfile(stp),
                    os.path.getsize(stp) if os.path.isfile(stp) else -1))
    with open(stp, "rb") as f:
        lines.append("STP 文件头: %r" % f.read(120))
except Exception:
    lines.append("STP: 失败\n%s" % traceback.format_exc())

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
