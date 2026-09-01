# -*- coding: utf-8 -*-
# Round-trip check: import each exported .x_t back into NX and count solid bodies.
import NXOpen
import NXOpen.UF
import os

SRC    = r"C:\Users\5600\Documents\ZDH\NX\stdparts"
OUTDIR = os.path.join(SRC, "NX8兼容_x_t")
TMP    = r"C:\Users\5600\Documents\ZDH\NX\stdparts\_nx_export\tmp"
TMPL   = os.path.join(os.environ.get("UGII_BASE_DIR", r"C:\Program Files\Siemens\NX2312"),
                      "UGII", "templates", "model-plain-1-mm-template.prt")
REPORT = os.path.join(SRC, "_nx_export", "verify.txt")

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

    xts = sorted([f for f in os.listdir(OUTDIR) if f.lower().endswith(".x_t")])
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
