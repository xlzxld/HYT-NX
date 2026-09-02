# -*- coding: utf-8 -*-
#
# NX8 ~ NX2312 : batch import Parasolid .x_t -> save as .prt
#
# HOW TO USE
#   1. Copy this whole folder (the xt\ subfolder with the .x_t files + this .py)
#      to the target NX machine.
#   2. Double click "一键导入.bat", or inside NX: File -> Execute -> NX Open.
#   3. Results land in the "x_t转prt" folder next to "xt". Check import_log.txt
#      (written next to this script).
#
# WHY THE ASCII STAGING
#   NX10 runs in locale mode (GBK on a Chinese Windows) by default. Handing it a
#   path that Chinese characters makes it throw:
#       "期望的是语言环境数据，但检测到 UTF8 数据。"
#   NX2312 defaults to UTF-8 and does not care, so this bites on NX10 only.
#   Fix: never give NX a non-ASCII path. Python does all the unicode work
#   (list / copy / rename - all unicode safe) and NX only ever sees pure-ASCII
#   staging paths. Afterwards Python renames the saved .prt to its Chinese name.
#
# NOTES
#   - Source folder = the "xt" subfolder next to this script (or pass a path as
#     an argument).
#   - Output folder = sibling folder of the source, named "x_t转prt".
#   - Output .prt format = whatever NX version runs this script (the .x_t
#     carrier itself is Parasolid 24.0, i.e. NX8 schema, readable by NX8+).
#   - UNITS: 1 = millimeter, 2 = inch. All 14 source parts are millimeters.
#   - Imported bodies have no feature history (Parasolid is dumb geometry).
#   - Python 2.7 (NX8~NX11) and Python 3 (NX1847+) compatible.
#
import NXOpen
import NXOpen.UF
import os
import sys
import shutil
import codecs

UNITS = 1              # 1 = millimeter, 2 = inch
OUT_DIRNAME = "x_t转prt"
LOG_NAME = "import_log.txt"

_lines = []


def w(msg):
    _lines.append(msg)
    try:
        NXOpen.Session.GetSession().LogFile.WriteLine(msg)
    except Exception:
        pass


def is_ascii(s):
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def script_dir():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return os.path.abspath(".")


def src_dir():
    for a in sys.argv[1:]:
        if os.path.isdir(a):
            return os.path.abspath(a)
    d = script_dir()
    xt = os.path.join(d, "xt")     # x_t 统一放在 xt 子目录
    if os.path.isdir(xt):
        return xt
    return d


def ascii_tmpdir(preferred_parent):
    """Find a pure-ASCII directory to stage files in."""
    cands = [os.path.join(preferred_parent, "_tmp")]
    try:
        import tempfile
        cands.append(os.path.join(tempfile.gettempdir(), "nx_xt_import"))
    except Exception:
        pass
    cands.append(os.path.join(os.path.expanduser("~"), "nx_xt_import"))
    cands.append(os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"),
                              "nx_xt_import"))
    cands.append("C:\\Windows\\Temp\\nx_xt_import")
    for c in cands:
        if is_ascii(c):
            return c
    return None


def main():
    s = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()

    src = src_dir()
    out = os.path.join(os.path.dirname(src), OUT_DIRNAME)
    if not os.path.isdir(out):
        os.makedirs(out)

    w("NX import-to-prt  by WorkBuddy")
    w("SRC = %s" % src)
    w("OUT = %s" % out)
    w("UNITS = %s (1=mm 2=inch)" % UNITS)

    tmp = ascii_tmpdir(out)
    if tmp is None:
        w("FATAL: no pure-ASCII staging directory available.")
        with codecs.open(os.path.join(script_dir(), LOG_NAME), "w", "utf-8") as f:
            f.write("\n".join(_lines))
        return
    if not os.path.isdir(tmp):
        os.makedirs(tmp)
    w("ASCII staging = %s" % tmp)

    xts = sorted([f for f in os.listdir(src) if f.lower().endswith(".x_t")])
    w("FOUND %d x_t file(s)" % len(xts))
    if not xts:
        w("ABORT: no .x_t in %s" % src)
        with codecs.open(os.path.join(script_dir(), LOG_NAME), "w", "utf-8") as f:
            f.write("\n".join(_lines))
        return

    ok = 0
    failed = []

    for i, name in enumerate(xts):
        xt = os.path.join(src, name)
        base = os.path.splitext(name)[0]
        final_prt = os.path.join(out, base + ".prt")
        stage_xt = os.path.join(tmp, "i%03d.x_t" % i)
        stage_prt = os.path.join(tmp, "i%03d.prt" % i)

        try:
            for p in (stage_xt, stage_prt):
                if os.path.exists(p):
                    os.remove(p)

            # Python copies the unicode-named file to an ASCII staging name.
            shutil.copyfile(xt, stage_xt)

            uf.Part.CloseAll()
            uf.Part.New(stage_prt, UNITS)      # NX only sees ASCII here
            wp = s.Parts.Work
            if wp is None:
                raise RuntimeError("UF_PART_new failed on ASCII stage path")

            uf.Ps.ImportData(stage_xt)         # and here

            bodies = [b for b in wp.Bodies]
            if not bodies:
                raise RuntimeError("imported 0 bodies")
            try:
                n_solid = len([b for b in bodies if b.IsSolidBody])
            except Exception:
                n_solid = -1

            uf.Part.Save()

            # Hand the Chinese name back. os.rename is unicode safe.
            if os.path.exists(final_prt):
                os.remove(final_prt)
            os.rename(stage_prt, final_prt)

            sz = os.path.getsize(final_prt) if os.path.exists(final_prt) else 0
            w("[OK  ] %-30s bodies=%d solids=%d size=%d"
              % (base, len(bodies), n_solid, sz))
            ok += 1

        except Exception as e:
            w("[FAIL] %-30s %s" % (base, str(e)))
            failed.append(base)
        finally:
            for p in (stage_xt, stage_prt):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

    try:
        uf.Part.CloseAll()
    except Exception:
        pass

    # 收尾: 暂存文件已逐个清空, 顺手删掉空目录壳; 删不掉(被占用)就留着, 不影响使用
    try:
        if os.path.isdir(tmp):
            os.rmdir(tmp)
    except Exception:
        pass

    w("DONE  ok=%d  fail=%d" % (ok, len(failed)))
    if failed:
        w("FAILED: %s" % ", ".join(failed))

    with codecs.open(os.path.join(script_dir(), LOG_NAME), "w", "utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    main()
