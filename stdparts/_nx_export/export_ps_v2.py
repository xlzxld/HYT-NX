# -*- coding: utf-8 -*-
# Export .prt -> Parasolid 24.0 (NX8 schema), with everything NX sees forced ASCII.
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

SRC = r"C:\Users\5600\Documents\ZDH\NX\stdparts"
OUT = r"C:\Users\5600\Documents\ZDH\NX\stdparts\_nx_export\new_xt"
STAGE = r"C:\Users\5600\Documents\ZDH\NX\stdparts\_nx_export\stage"
LOG = r"C:\Users\5600\Documents\ZDH\NX\stdparts\_nx_export\export_v2.txt"

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


if __name__ == "__main__":
    main()
