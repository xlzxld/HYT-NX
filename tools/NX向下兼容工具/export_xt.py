# -*- coding: utf-8 -*-
# Export .prt -> Parasolid 24.0 (NX8 schema), with everything NX sees forced ASCII.
# Run inside NX2312 (File -> Execute -> NX Open). Output .x_t lands in the "xt"
# subfolder of this package, ready for import_xt_to_prt.py on a lower-version NX.
#
# Why: NX writes the source part name into the .x_t header. A Chinese part name
# becomes UTF-8 bytes inside the file, and NX10 in locale mode (GBK) rejects it:
#   "期望的是语言环境数据，但检测到 UTF8 数据。"
# So: copy each .prt to an ASCII staging name, export, then rename the result to
# its Chinese name with Python (unicode safe). NX never sees a non-ASCII path
# and never bakes a non-ASCII name into the file.
import NXOpen
import os
import shutil
import codecs

_HERE = os.path.dirname(os.path.abspath(__file__))   # tools\NX向下兼容工具
_ROOT = os.path.dirname(os.path.dirname(_HERE))      # project root
SRC   = os.path.join(_ROOT, "stdparts")
OUT   = os.path.join(_HERE, "xt")                    # 产物 x_t 统一放 xt 子目录
STAGE = os.path.join(_HERE, "stage")                 # ASCII 暂存区, 跑完自动删
LOG   = os.path.join(_HERE, "export_log.txt")

_lines = []


def w(msg):
    _lines.append(msg)
    try:
        NXOpen.Session.GetSession().LogFile.WriteLine(msg)
    except Exception:
        pass


def main():
    s = NXOpen.Session.GetSession()
    V = NXOpen.ParasolidExporter.ParasolidVersionOption
    EXISTING = getattr(NXOpen.ParasolidExporter.ExportFromOption, "ExistingPart")
    PS_NX8 = getattr(V, "Ps240Nx80")

    for d in (OUT, STAGE):
        if not os.path.isdir(d):
            os.makedirs(d)

    prts = sorted([f for f in os.listdir(SRC) if f.lower().endswith(".prt")])
    w("TOTAL = %d" % len(prts))

    ok = 0
    failed = []

    for i, name in enumerate(prts):
        base = os.path.splitext(name)[0]
        src_prt = os.path.join(SRC, name)
        final_xt = os.path.join(OUT, base + ".x_t")
        stage_prt = os.path.join(STAGE, "p%03d.prt" % i)
        stage_xt = os.path.join(STAGE, "p%03d.x_t" % i)
        try:
            for p in (stage_prt, stage_xt):
                if os.path.exists(p):
                    os.remove(p)

            shutil.copyfile(src_prt, stage_prt)      # ASCII name, ASCII path

            exp = s.DexManager.CreateParasolidExporter()
            try:
                exp.ExportFrom = EXISTING
                exp.InputFile = stage_prt
                exp.ObjectTypes.Solids = True
                exp.ObjectTypes.Surfaces = True
                exp.ObjectTypes.Curves = True
                exp.FlattenAssembly = True
                exp.ParasolidVersion = PS_NX8
                exp.OutputFile = stage_xt
                exp.Commit()
            finally:
                exp.Destroy()

            if not os.path.exists(stage_xt):
                raise RuntimeError("no output produced")

            if os.path.exists(final_xt):
                os.remove(final_xt)
            os.rename(stage_xt, final_xt)              # hand back the Chinese name

            with open(final_xt, "rb") as f:
                data = f.read()
            na = sum(1 for c in data if c > 127)
            w("[OK  ] %-30s size=%-9d non_ascii_bytes=%d" % (base, len(data), na))
            ok += 1
        except Exception as e:
            w("[FAIL] %-30s %s" % (base, str(e)))
            failed.append(base)
        finally:
            for p in (stage_prt, stage_xt):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

    w("DONE ok=%d fail=%d" % (ok, len(failed)))
    with codecs.open(LOG, "w", "utf-8") as f:
        f.write("\n".join(_lines))

    # 收尾: stage 里的文件已逐个清空, 顺手删掉空目录壳; 删不掉(被占用)就留到下次
    try:
        if os.path.isdir(STAGE):
            os.rmdir(STAGE)
    except Exception:
        pass


if __name__ == "__main__":
    main()
