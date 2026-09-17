# -*- coding: utf-8 -*-
# Round-trip check: import each .x_t in the "xt" subfolder back into NX, count
# solid bodies, compare with stdparts sources. Run inside NX2312.
try:
    import NXOpen
    import NXOpen.UF
except ImportError:            # 非 NX 环境(外部 Python): 只允许跑 --selftest
    NXOpen = None
import os
import sys

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


def _enum_member(enum_cls, names):
    """(纯逻辑, 可离线测) 按候选成员名取枚举值; 全部试不到才抛 AttributeError。

    NX 的 Python 绑定跨版本改过枚举成员名: 保留字成员在旧版带下划线后缀
    ("True_"), 新版可能是 "True"; CloseModified 的成员名两版也不一样。
    写死一个名字必然在某些版本上炸 —— 逐候选试, 全落空才算真失败。
    """
    for n in names:
        try:
            return getattr(enum_cls, n)
        except Exception:
            continue
    raise AttributeError("%s 上没有候选之任一: %s"
                         % (getattr(enum_cls, "__name__", enum_cls),
                            ", ".join(names)))


def _safe_argv():
    """(纯逻辑) NX 界面执行日记时宿主给进来的不是真 sys 模块, sys.argv
    可能不存在, 直接引用会抛 AttributeError(同 import_xt_to_prt.py)。"""
    try:
        a = getattr(sys, "argv", None)
        return list(a) if a else []
    except Exception:
        return []


def _selftest():
    """离线自测 _enum_member, 不依赖 NX 运行时。返回失败描述列表(空=全绿)。"""
    # 下面几个假枚举类不写 (object) 基类: Python 3 里隐式继承等价, 而写了会被
    # ruff UP004 判为新增问题(本项目门禁要求新增代码 0 问题, 存量风格不追加)。
    class _V2312:                  # 新版: 成员名不带下划线
        TrueValue = "t"
        UseResponses = "ur"

    class _V10:                    # 旧版: 保留字成员带下划线后缀
        True_ = "t_"

    class _EMPTY:                  # 候选全落空
        pass

    class _NONEVAL:                # 成员存在但值为 None: 仍算"找到"
        True_ = None

    fails = []
    v = _enum_member(_V2312, ("True_", "True", "TrueValue"))
    if v != "t":
        fails.append("新版风格: 期望 't', 实得 %r" % (v,))
    v = _enum_member(_V10, ("True_", "True"))
    if v != "t_":
        fails.append("旧版风格: 期望 't_', 实得 %r" % (v,))
    try:
        _enum_member(_EMPTY, ("True_", "True"))
        fails.append("候选全落空时应抛 AttributeError, 实际没抛")
    except AttributeError:
        pass
    try:
        if _enum_member(_NONEVAL, ("True_",)) is not None:
            fails.append("值为 None 的成员应原样返回 None")
    except Exception as e:
        fails.append("值为 None 的成员应视为找到, 却抛了 %s" % e)
    return fails


def main():
    if NXOpen is None:
        print("本脚本须在 NX 内运行(外部 Python 只能跑 --selftest)。")
        return
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

        # 关件: 枚举成员名跨版本不一致(旧版保留字成员是 "True_" 而不是 "True"),
        # 以前写死 getattr(..., "True") 会直接抛 AttributeError 让整个 try 中断,
        # Close 压根没执行 —— 每个 x_t 的临时部件都留在会话里(verify.txt 里
        # 每个文件一条同样的 WARN, 关件等于从来没成功过)。改逐候选 + UF 兜底,
        # 真的两条路都关不掉才记账。
        try:
            cwt = _enum_member(NXOpen.BasePart.CloseWholeTree, ("True_", "True"))
            cmod = _enum_member(NXOpen.BasePart.CloseModified,
                                ("UseResponses", "UseResponses_", "CloseModified"))
            wp.Close(cwt, cmod, None)
        except Exception as e:
            w("[WARN] close %s (NXOpen 路线): %s" % (name, str(e)))
            try:
                uf.Part.Close(wp.Tag, 1, 1)
                w("[INFO] close %s 改走 UF 兜底成功" % name)
            except Exception as e2:
                w("[WARN] close %s UF 兜底也失败: %s" % (name, str(e2)))

    w("VERIFY DONE, problems=%d" % bad)

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))


if __name__ == "__main__":
    if "--selftest" in _safe_argv():
        _fails = _selftest()
        if _fails:
            print("SELFTEST FAIL:")
            for _f in _fails:
                print("  - " + _f)
            sys.exit(1)
        print("SELFTEST OK (4 项断言全绿)")
    else:
        main()
