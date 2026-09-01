# -*- coding: utf-8 -*-
#
# apply_zero_offsets.py — 一次性迁移: 按用户 2026-09-02 实测的 14 个定位点,
# 批量生成归零副本到 stdparts_归零/。
# 机制: 新建输出部件 → 原件以组件方式放在 −定位点 → 提升独立体 →
#       移除参数(哑实体) → 删组件壳 → 保存。原始 stdparts 一律不动。
# 运行: run_journal.exe apply_zero_offsets.py (批处理, 无界面)
#
import os
import sys
import time

import NXOpen
import NXOpen.UF

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "stdparts")
OUT = os.path.join(BASE, "stdparts_归零")

# 文件名 → 定位点(零件坐标系 mm, 用户在 NX2312 实测)
POINTS = {
    "主进胶与中心定位垫片-30.prt": (1497.720729, -110.804788, -124.579524),
    "主进胶与中心定位垫片-35.prt": (1647.720690, -110.804765, -124.579500),
    "压线板.prt": (100.961986, 192.963470, -329.500000),
    "垫片.prt": (2157.282272, -395.734674, -315.188852),
    "大水口-18.prt": (1107.282272, -395.734674, -420.188852),
    "大水口-25.prt": (1257.282272, -395.734674, -420.188852),
    "大水口-35.prt": (1407.282272, -395.734674, -420.188852),
    "接线盒-16针.prt": (0.000000, 830.000000, 18.100000),
    "接线盒-24针.prt": (0.000000, 830.000000, 98.100000),
    "接线盒-48针.prt": (67.498639, 68.188863, -71.510357),
    "点胶口-18.prt": (1594.782272, -395.734674, -570.188852),
    "点胶口-25.prt": (1473.782272, -395.734674, -413.531357),
    "螺丝-45.prt": (445.000000, -86.551750, 89.500000),
    "螺丝-50.prt": (338.492122, -239.339670, 0.000000),
}


def log(msg):
    try:
        NXOpen.Session.GetSession().LogFile.WriteLine(msg)
    except Exception:
        pass
    print(msg)


def add_component(runner, part, src, name, pos):
    """恒等姿态组件放置, 引用集 Entire Part→MODEL 降级。"""
    import NXOpen
    ca = part.ComponentAssembly
    m3 = runner._matrix3x3(NXOpen, False)
    last = None
    for refset in ("Entire Part", "MODEL"):
        try:
            try:
                comp, _ls = ca.AddComponent(src, refset, name, pos, m3, -1)
            except TypeError:
                comp = ca.AddComponent(src, refset, name, pos, m3, -1, False)
            log("  引用集: %s" % refset)
            return comp
        except Exception as ex:
            last = ex
    raise RuntimeError("组件放置失败: %s" % last)


def enter_modeling(session):
    """已由"模型模板复制"路线取代: 模板自带建模应用记录。保留兜底提示。"""
    return False


def model_template_path():
    """NX"模型"模板路径(mm)。"""
    import os
    cands = []
    base = os.environ.get("UGII_BASE_DIR")
    if base:
        cands.append(os.path.join(base, "UGII", "templates",
                                  "model-plain-1-mm-template.prt"))
    cands += [
        r"C:\Program Files\Siemens\NX2312\UGII\templates\model-plain-1-mm-template.prt",
        r"C:\Program Files\Siemens\NX2306\UGII\templates\model-plain-1-mm-template.prt",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def process(session, uf, runner, src, out, p):
    import NXOpen
    fname = os.path.basename(src)
    stem = os.path.splitext(fname)[0]
    px, py, pz = p
    # 部件内部名不能与原件相同(同名组件放置会被 NX 当成循环装配),
    # 用毫秒戳临时名; 且从"模型"模板复制而来, 输出件打开时直接进入建模。
    tmpl = model_template_path()
    tmp = os.path.join(OUT, "_staging_%s_%d.prt"
                       % (stem, int(time.time() * 1000)))
    try:
        import shutil
        if tmpl:
            shutil.copyfile(tmpl, tmp)
            log("  基础: 模型模板(建模应用已内置)")
        else:
            log("  提示: 找不到模型模板, 输出件打开时需手动进入建模。")
            uf.Part.New(tmp, 1)           # 1 = mm
    except Exception as ex:
        raise RuntimeError("创建输出部件失败: %s" % ex)
    ret = uf.Part.Open(tmp)
    tag = ret[0] if isinstance(ret, tuple) else ret
    try:
        uf.Part.SetDisplayPart(tag)
    except Exception:
        pass
    part = session.Parts.Display
    if part is None:
        raise RuntimeError("新建部件后拿不到显示部件")
    try:
        session.Parts.SetWork(part)
    except Exception:
        try:
            uf.Assem.SetWorkPart(tag)
        except Exception:
            pass
    enter_modeling(session)

    comp = add_component(runner, part, src, "ZERO_%s" % stem,
                         NXOpen.Point3d(-px, -py, -pz))
    bodies = runner._promote_body(
        part, comp, "ZEROREF_%s" % stem,
        lambda m: log("  " + m), body_index=None)
    bodies = [b for b in (bodies or []) if b is not None]
    runner._remove_parameters(session, part, bodies,
                              lambda m: log("  " + m))
    try:
        session.UpdateManager.AddToDeleteList([comp])
        session.UpdateManager.DoUpdate(
            session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                "迁移 删组件壳"))
    except Exception as ex:
        log("  删组件壳失败(输出件会多一个隐藏引用): %s" % ex)
    # SaveAs 到最终名会被 NX 拒绝(会话里已加载的原件与其内部名同名,
    # 报 "File already exists")——改走: 存临时名 → 关部件 → 磁盘改名。
    try:
        uf.Part.Save()                     # 无参形式, 保存当前工作部件
    except Exception:
        sc = getattr(NXOpen.BasePart.SaveComponents, "True_",
                     getattr(NXOpen.BasePart.SaveComponents, "True", None))
        ca_ = getattr(NXOpen.BasePart.CloseAfterSave, "False_",
                      getattr(NXOpen.BasePart.CloseAfterSave, "False", None))
        part.Save(sc, ca_)
    try:
        uf.Part.Close(tag, 1, 1)
    except Exception:
        pass
    try:
        os.replace(tmp, out)
    except OSError as ex:
        raise RuntimeError("改名 %s → %s 失败: %s" % (tmp, out, ex))
    log("  %s: 副本 %d 实体, 位移 (%.6f, %.6f, %.6f) → 已保存"
        % (fname, len(bodies), -px, -py, -pz))
    return len(bodies)


def main():
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    try:
        sys.path.insert(0, BASE)
        import nx_extrude_runner as runner
    except Exception as ex:
        log("无法导入主脚本: %s" % ex)
        return 1
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    log("==== 批量归零迁移: %d 件 ====" % len(POINTS))
    ok = fail = 0
    for fname in sorted(POINTS):
        p = POINTS[fname]
        src = os.path.join(SRC, fname)
        out = os.path.join(OUT, fname)
        if not os.path.isfile(src):
            log("跳过(缺文件): %s" % fname)
            fail += 1
            continue
        try:
            process(session, uf, runner, src, out, p)
            ok += 1
        except Exception as ex:
            fail += 1
            log("失败 %s: %s" % (fname, ex))
    log("==== 迁移完成: 成功 %d, 失败 %d。输出: %s ====" % (ok, fail, OUT))
    return 0 if fail == 0 else 2


rc = main()
if os.environ.get("ZERO_REF_CLI"):
    sys.exit(rc)
