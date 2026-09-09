# -*- coding: utf-8 -*-
"""
nx_mold_cut_runner.py —— 模具自动开框 NX 日记入口 (v1.3)
=============================================================================
适用环境：Siemens NX 10 / NX 12 / NX 2312 及以上版本
播放方式与 batch_smoke 相同：NX 菜单 工具 → 日记 → 播放，选本文件。

【前提(用户工作流)】
  1. 已用 nx_extrude_runner.py 跑完分层拉伸流水线(本脚本不做任何建模);
  2. 模具已手动放置到当前工作部件并摆好位置(本脚本不引入任何文件)。

【作用】
  部件内带 CAD3D 标记的体 = 工具体(分流板/加热条/标准件等), 未带标记的体 =
  模具。接触处自动布尔减去(工具体保留)。试切可配置(nx_std_config.py):
    MOLD_TRIAL_CUT = True  → 开启试切: 对 conflict_check 启用的类型减前先
                             试切对比孔壁, 会破坏模具已有孔(如孔边螺丝)则
                             撤销并跳过该件;
    MOLD_TRIAL_CUT = False → 关闭试切: 全部直接减去, 不做冲突检查。
  (出线槽倒圆/扩孔等减后处理已搁置: 代码保留, 默认不配置即不执行。)
  重跑安全: 已开框处以"无交集"记日志跳过, 不会报错或破坏部件。
  类型标记 CAD3D_TYPE 由流水线打标, 旧产物无标记按默认规则处理。

【模式（改下方 MODE 后重新播放）】
  "cut" —— 执行自动开框(默认)。
  "api" —— 只读探针: 列出本 NX 可用的边规则/倒圆/偏置等 API 名, 写
           logs/mold_api_probe.txt。天侧倒圆或偏置被跳过时先跑这个。

【产出判读】控制台最后一行 + logs/mold_cut_report.txt:
  MOLD RESULT ok=True tools=84 mold=N cuts=K skip=S fail=F conflict=C
"""

import io
import os
import sys

# ----------------------------------------------------------------------------
# 路径引导与 cad3d 模块缓存驱逐(与 nx_extrude_runner 同款, 确保重放加载最新代码)
# ----------------------------------------------------------------------------
sys.dont_write_bytecode = True
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

for _mod in list(sys.modules.keys()):
    if _mod == "cad3d" or _mod.startswith("cad3d."):
        del sys.modules[_mod]

from cad3d.core.paths import _logs_dir

MODE = "cut"             # "cut"=执行自动开框; "api"=只读探测本NX可用API


def _save_report(name, lines):
    p = os.path.join(_logs_dir(), name)
    try:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("report -> %s" % p)
    except OSError as ex:
        print("report 写入失败: %s" % ex)
    return p


def api_probe():
    """只读探针: 枚举本 NX 的边规则/倒圆/偏置/删面/求交等 API 名, 供跨版本适配。"""
    import NXOpen
    import NXOpen.UF

    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        print("API PROBE RESULT ok=False reason=no_work_part")
        return
    uf = NXOpen.UF.UFSession.GetUFSession()
    keys = ("Edge", "Offset", "Blend", "Rule", "DeleteFace", "Promotion",
            "Intersect", "Interference", "Clearance", "Containment", "Point")
    lines = ["本 NX 可用 API 探针(NXOpen 对象方法枚举, 只读无副作用)"]
    for label, obj in (("ScRuleFactory", work_part.ScRuleFactory),
                       ("Features", work_part.Features),
                       ("ScCollectors", work_part.ScCollectors),
                       ("UF.Modeling", uf.Modeling)):
        try:
            names = sorted(n for n in dir(obj)
                           if any(k in n for k in keys))
        except Exception as ex:
            lines.append("%s: 枚举失败 %s" % (label, ex))
            continue
        lines.append("")
        lines.append("[%s] %d 个" % (label, len(names)))
        lines.extend("  %s.%s" % (label, n) for n in names)
    _probe_live(lines, uf, work_part)
    _save_report("mold_api_probe.txt", lines)
    print("API PROBE RESULT ok=True")


def _probe_live(lines, uf, work_part):
    """求交类接口活性测试(只读): 用部件内真实体逐签名试调, 结果写入报告。

    用于确定 AskPointContainment/CheckInterference 在本 NX 的确切调用方式
    与返回值形态, 供 mold_cut 预筛的跨版本探测链取证。
    """
    lines.append("")
    lines.append("== 求交类接口活性测试(只读, 不建几何) ==")
    bodies = []
    try:
        for b in work_part.Bodies:
            bodies.append(b)
            if len(bodies) >= 2:
                break
    except Exception:
        pass
    if not bodies:
        lines.append("  部件内无体, 跳过活性测试。")
        return
    b1 = bodies[0]
    t1 = b1.Tag
    pt = [0.0, 0.0, 0.0]
    try:
        for e in b1.GetEdges():
            p = e.StartPoint
            pt = [float(p.X), float(p.Y), float(p.Z)]
            break
    except Exception:
        pass
    lines.append("  测试体 Tag=%s, 测试点=%r" % (t1, pt))

    def _try(desc, fn):
        try:
            lines.append("  %s -> OK 返回 %r" % (desc, fn()))
        except TypeError as ex:
            lines.append("  %s -> TypeError(签名不符): %s" % (desc, ex))
        except Exception as ex:
            lines.append("  %s -> %s: %s" % (desc, type(ex).__name__, ex))

    ask_pc = getattr(uf.Modeling, "AskPointContainment", None)
    if ask_pc is None:
        lines.append("  AskPointContainment: 不存在")
    else:
        _try("ask(tag, [x,y,z])", lambda: ask_pc(t1, pt))
        _try("ask(tag, x, y, z)",
             lambda: ask_pc(t1, pt[0], pt[1], pt[2]))
        _try("ask([tag], [x,y,z])", lambda: ask_pc([t1], pt))
        _try("ask(num, [tag], [x,y,z])", lambda: ask_pc(1, [t1], pt))
        _try("ask([x,y,z], tag)", lambda: ask_pc(pt, t1))
        _try("远点对照 ask(tag, [x+1000,y,z])",
             lambda: ask_pc(t1, [pt[0] + 1000.0, pt[1], pt[2]]))
    if len(bodies) > 1:
        t2 = bodies[1].Tag
        chk = getattr(uf.Modeling, "CheckInterference", None)
        if chk is None:
            lines.append("  CheckInterference: 不存在")
        else:
            _try("chk(tag1, tag2)", lambda: chk(t1, t2))
            _try("chk(tag1, tag2, 0.0)", lambda: chk(t1, t2, 0.0))
            _try("chk(tag1, tag2, 0)", lambda: chk(t1, t2, 0))
            _try("chk([tag1, tag2])", lambda: chk([t1, t2]))
    else:
        lines.append("  CheckInterference: 部件内不足两体, 跳过")
    lines.append("  (IntersectBodies 有几何副作用, 未做活性测试)")


def main():
    import NXOpen

    from cad3d.core.logging import Log
    from cad3d.modeling.mold_cut import cut_mold

    if MODE == "api":
        api_probe()
        return
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        print("MOLD RESULT ok=False reason=no_work_part")
        print("!! 请先打开/新建包含 模具 + CAD3D 产物 的工作部件, 再播放本日记。")
        return
    log = Log(session)
    log("【模具开框】工作部件: %s" % work_part.Name)
    st = cut_mold(session, work_part, log)
    _save_report("mold_cut_report.txt", log.lines)
    print("MOLD RESULT ok=%s tools=%d mold=%d cuts=%d skip=%d fail=%d "
          "conflict=%d post=%d"
          % (st.get("ok"), st.get("tools", 0), st.get("mold", 0),
             st.get("cuts", 0), st.get("skip", 0), st.get("fail", 0),
             st.get("conflict", 0), st.get("post", 0)))


if __name__ == "__main__":
    main()
