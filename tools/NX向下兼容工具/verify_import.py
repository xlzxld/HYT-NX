# -*- coding: utf-8 -*-
# Round-trip check: import each .x_t in the "xt" subfolder back into NX, count
# solid bodies, compare with stdparts sources. Run inside NX2312.
import NXOpen
import NXOpen.UF
import os

_HERE  = os.path.dirname(os.path.abspath(__file__))   # tools\NX向下兼容工具
_ROOT  = os.path.dirname(os.path.dirname(_HERE))      # project root
SRC    = os.path.join(_ROOT, "stdparts")
OUTDIR = os.path.join(_HERE, "xt")                    # x_t 都在 xt 子目录
TMP    = os.path.join(_HERE, "tmp")
TMPL   = os.path.join(os.environ.get("UGII_BASE_DIR", r"C:\Program Files\Siemens\NX2312"),
                      "UGII", "templates", "model-plain-1-mm-template.prt")
REPORT = os.path.join(_HERE, "verify.txt")

_lines = []


def w(msg):
    _lines.append(msg)
    try:
        NXOpen.Session.GetSession().LogFile.WriteLine(msg)
    except Exception:
        pass


def main():
    s = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    if not os.path.isdir(TMP):
        os.makedirs(TMP)

    xts = sorted([f for f in os.listdir(OUTDIR) if f.lower().endswith(".x_t")]) \
        if os.path.isdir(OUTDIR) else []
    if not xts:
        w("VERIFY ABORT: no .x_t in %s (run export_xt.py first)" % OUTDIR)
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        return
    w("VERIFY %d files" % len(xts))
    bad = 0

    for i, name in enumerate(xts):
        xt = os.path.join(OUTDIR, name)
        tmp_prt = os.path.join(TMP, "chk_%02d.prt" % i)
        if os.path.exists(tmp_prt):
            os.remove(tmp_prt)
        try:
            r = uf.Part.New(tmp_prt, 1)   # 1 = millimeters
            if isinstance(r, tuple):
                r = r[-1]
            w("[INFO] %s  new-part rc=%s" % (name, str(r)))
        except Exception as e:
            w("[ERR ] %s  new-part: %s" % (name, str(e)))
            bad += 1
            continue

        try:
            uf.Ps.ImportData(xt)
        except Exception as e:
            w("[ERR ] %s  import: %s" % (name, str(e)))
            bad += 1

        wp = s.Parts.Work
        bodies = [b for b in wp.Bodies]
        solid = [b for b in bodies if b.IsSolidBody]
        w("[OK  ] %s  bodies=%d solids=%d" % (name, len(bodies), len(solid)))
        if len(solid) == 0:
            bad += 1

        try:
            cwt = getattr(NXOpen.BasePart.CloseWholeTree, "True")
            wp.Close(cwt, NXOpen.BasePart.CloseModified.UseResponses, None)
        except Exception as e:
            w("[WARN] close %s: %s" % (name, str(e)))

    w("VERIFY DONE, problems=%d" % bad)

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
