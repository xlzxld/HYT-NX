# -*- coding: utf-8 -*-
# NX2312 batch journal: export .prt -> Parasolid .x_t at an older schema version
# No downgrade-save exists for .prt, so Parasolid is the compatibility carrier.
import NXOpen
import os

SRC     = r"C:\Users\5600\Documents\ZDH\NX\stdparts"
OUTDIR  = os.path.join(SRC, "NX8兼容_x_t")
OUTDIR2 = os.path.join(SRC, "NX10兼容_x_t")   # fallback, only if PS24 fails
REPORT  = os.path.join(SRC, "_nx_export", "report.txt")

_lines = []


def w(msg):
    _lines.append(msg)
    try:
        NXOpen.Session.GetSession().LogFile.WriteLine(msg)
    except Exception:
        pass


def pick(enum_type, names):
    for n in names:
        if hasattr(enum_type, n):
            return getattr(enum_type, n)
    raise RuntimeError("enum missing: %s / have=%s" % (names, dir(enum_type)))


def do_export(prt, outfile, ver):
    s = NXOpen.Session.GetSession()
    if os.path.exists(outfile):
        os.remove(outfile)
    exp = s.DexManager.CreateParasolidExporter()
    try:
        exp.ExportFrom = EXISTING
        exp.InputFile = prt
        exp.ObjectTypes.Solids = True
        exp.ObjectTypes.Surfaces = True
        exp.ObjectTypes.Curves = True
        exp.FlattenAssembly = True
        exp.ParasolidVersion = ver
        exp.OutputFile = outfile
        exp.Commit()
    finally:
        exp.Destroy()
    return os.path.exists(outfile) and os.path.getsize(outfile) > 0


def schema_of(path):
    try:
        with open(path, "r") as f:
            head = f.read(400)
        for tok in head.replace("\r", "\n").split("\n"):
            if "SCH" in tok.upper() and tok.strip():
                return tok.strip()[:80]
    except Exception:
        pass
    return "?"


def main():
    global EXISTING
    s = NXOpen.Session.GetSession()
    E = NXOpen.ParasolidExporter
    EXISTING = pick(E.ExportFromOption,
                    ["ExistingPart", "ExportFromOptionExistingPart"])
    V = E.ParasolidVersionOption
    PS_NX8  = pick(V, ["Ps240Nx80", "ParasolidVersionOptionPs240Nx80"])
    PS_NX10 = pick(V, ["Ps270Nx100", "ParasolidVersionOptionPs270Nx100"])

    w("PS240=%s  PS270=%s  EXISTING=%s" % (PS_NX8, PS_NX10, EXISTING))

    for d in (OUTDIR, OUTDIR2):
        if not os.path.isdir(d):
            os.makedirs(d)

    prts = sorted([f for f in os.listdir(SRC) if f.lower().endswith(".prt")])
    w("TOTAL PARTS = %d" % len(prts))

    ok8, ok10, failed = [], [], []

    for name in prts:
        prt = os.path.join(SRC, name)
        base = os.path.splitext(name)[0]
        out8 = os.path.join(OUTDIR, base + ".x_t")
        try:
            good = do_export(prt, out8, PS_NX8)
        except Exception as e:
            good = False
            w("[ERR ] %s  PS24 -> %s" % (name, str(e)))
        if good:
            ok8.append(name)
            w("[OK  ] %s -> PS24.0  %d bytes  hdr=%s" %
              (name, os.path.getsize(out8), schema_of(out8)))
        else:
            out10 = os.path.join(OUTDIR2, base + ".x_t")
            try:
                good2 = do_export(prt, out10, PS_NX10)
            except Exception as e:
                good2 = False
                w("[ERR ] %s  PS27 -> %s" % (name, str(e)))
            if good2:
                ok10.append(name)
                w("[FALL] %s -> PS27.0  %d bytes  hdr=%s" %
                  (name, os.path.getsize(out10), schema_of(out10)))
            else:
                failed.append(name)
                w("[FAIL] %s  both versions failed" % name)

    w("SUMMARY  PS24=%d  PS27=%d  FAILED=%d" % (len(ok8), len(ok10), len(failed)))
    w("FAILED LIST: %s" % ",".join(failed))

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
