# -*- coding: utf-8 -*-
"""
nx_zero_ref.py — 标准件定位点归零工具 v2
========================================

解决什么问题:
    主脚本放置公式是 "图纸定位点 − ref + 偏移", 其中 ref(零件坐标系里的插入
    基准点)需要你用测量工具量出精确 XYZ 再手工填进 nx_std_config.py。
    本工具把每个标准件 prt 的几何整体平移, 让定位点正好落在零件原点(0,0,0),
    之后 ref 全部写 [0,0,0], 配置表不再需要维护坐标。

工作流程(与用户确认的 v2 方案):
    1. 选择窗口 —— 复用主脚本的标准件选择对话框, 默认全选; 取消=退出。
    2. 加载预览 —— 选中各件的实体提升复制进当前工作部件(真实几何,
       捕捉必然可用), 按 Entire Part→MODEL 引用集逐个尝试并核对实体
       数量齐全; **立即移除参数成哑实体**(与组件壳彻底脱钩, 隐藏/删除
       组件壳不影响副本); 每件实体命名 ZERO_件名#序号。
    3. 逐件定位 —— 依序弹"指定点"对话框: 点控件后在图形区拾取该件定位点
       (支持捕捉), 核对坐标后点确定; 脚本当场把该件副本平移到 0,0,0,
       所见即所得。取消 = 中止拾点(已确认的件仍然有效)。
    4. 清理 —— 删除当前部件里的 ZERO_ 副本实体(全程 UndoMark,
       Ctrl+Z 可回滚)。
    5. 写回文件 —— 按记录的位移逐件: 打开原始 prt → 整体平移 → 另存
       stdparts_归零/ → 关闭(无 UI, 很快)。原始 prt 一律不动。

用法(NX 2312, 只适配这一版):
    工具 → 日记 → 播放 → 选本文件, 按上述流程走。
    --part 关键词   只处理文件名含关键词的件
    --point x,y,z   单件测量数据式: 不弹任何对话框, 直接对 --part 指定的件
                    按给定定位点写回(配合 MANUAL_ARGS 或命令行使用)
    --dry-run       写回阶段只打印位移, 不另存文件
    --out 目录名    输出文件夹名(默认 stdparts_归零)

注意:
    - 预览副本放在工具自建的临时部件里(显示会切过去), 结束时自动丢弃,
      你打开的部件不会被改动, 退出 NX 也不会残留"未保存更改"。
    - 点选/选择框必须在 NX 图形界面里跑(日记播放); run_journal 批处理
      会话只能用 --point 方式。
    - 写回前建议手动备份 stdparts 一次(与项目习惯一致); 替换完成后由
      助手把配置表 ref 清零(v1.36 发布步骤)。
"""

import argparse
import io
import math
import os
import shlex
import sys
import time

SCRIPT_VERSION = "1.36"
OUT_DIRNAME = "stdparts_归零"
SRC_DIRNAME = "stdparts"
GROUP_PREFIX = "ZERO_"
FEAT_PREFIX = "ZEROREF_"
TOL_ZERO = 1e-6          # 平移量小于此值视为"已在原点"

# 文件头手填参数(日记播放无法带命令行参数时的入口)。
# 示例: MANUAL_ARGS = "--part 接线盒-24.prt --point 12.5,0,-3.2"
MANUAL_ARGS = ""

# 当前预览临时部件登记(main 的 finally 统一丢弃, 不留"未保存更改")
_PREVIEW_PART = {"part": None, "path": None}


# ---------------------------------------------------------------------------
# 纯逻辑(无 NX 依赖, --selftest 覆盖这一段)
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="nx_zero_ref.py", description="标准件定位点归零工具")
    p.add_argument("--part", default=None,
                   help="只处理这一个文件(文件名包含即可, 如 接线盒-24)")
    p.add_argument("--point", default=None,
                   help="测量数据式: 定位点坐标 \"x,y,z\"(零件坐标系 mm), "
                        "须配合 --part; 不给则走完整点选流程")
    p.add_argument("--dry-run", action="store_true",
                   help="写回阶段只打印位移, 不另存文件")
    p.add_argument("--out", default=None,
                   help="输出文件夹名(默认 %s)" % OUT_DIRNAME)
    p.add_argument("--selftest", action="store_true",
                   help="无 NX 纯逻辑自测")
    return p


def parse_args(argv):
    """容错解析: NX 注入的额外 argv 项一律忽略。"""
    ns, _unknown = build_parser().parse_known_args(argv)
    return ns


def parse_xyz(text):
    """\"x,y,z\" → (float,float,float); 非法抛 ValueError。"""
    parts = [t.strip() for t in str(text).split(",")]
    if len(parts) != 3:
        raise ValueError("坐标必须是 x,y,z 三个数: %r" % text)
    vals = tuple(float(t) for t in parts)
    for v in vals:
        if not (-1e12 < v < 1e12):
            raise ValueError("坐标分量超出合理范围: %r" % text)
    return vals


def effective_argv(argv):
    """日记播放(sys.argv 只有脚本自身)时回退到文件头 MANUAL_ARGS。"""
    if len(argv) > 1:
        return list(argv[1:])
    text = (MANUAL_ARGS or "").strip()
    if not text:
        return []
    return shlex.split(text, posix=False)


def project_root(script_file):
    """项目根 = 本工具所在目录(tools)的上一级。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(script_file)))


def src_dir_of(script_file):
    return os.path.join(project_root(script_file), SRC_DIRNAME)


def out_dir_of(script_file, override=None):
    return os.path.join(project_root(script_file),
                        override if override else OUT_DIRNAME)


def list_prt_files(src_dir):
    if not os.path.isdir(src_dir):
        return []
    return sorted(f for f in os.listdir(src_dir)
                  if f.lower().endswith(".prt")
                  and os.path.isfile(os.path.join(src_dir, f)))


def filter_files(files, part_key):
    if not part_key:
        return list(files)
    key = part_key.lower()
    return [f for f in files if key in f.lower()]


def out_path_for(out_dir, fname):
    return os.path.join(out_dir, fname)


def delta_for(px, py, pz):
    return (-px, -py, -pz)


def is_at_origin(px, py, pz, tol=TOL_ZERO):
    return abs(px) < tol and abs(py) < tol and abs(pz) < tol


def fmt_point(p):
    return "(%.6f, %.6f, %.6f)" % (p[0], p[1], p[2])


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _blk_label(bid, text):
    return (
        '<Property class="UICOMP_label" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Label/Bitmap" type="uicomp">'
        '<item Expanded="1" class="UICOMP_label" hierarchy="" icon="styler_label.bmp" id="{id}" '
        'name="{id}" notes="" presentation="Label/Bitmap" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{text}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_label" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, text=_esc(text))


def _blk_point(bid, title):
    """UICOMP_point("Specify Point")块, 语法仿主脚本 _blk_double 最简风格
    (控件类名/图标取自 NX 自带模板 AECDefinition.dlx)。"""
    return (
        '<Property class="UICOMP_point" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Specify Point" type="uicomp">'
        '<item Expanded="1" class="UICOMP_point" hierarchy="" icon="inferpoint.bmp" id="{id}" '
        'name="{id}" notes="" presentation="Specify Point" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="Group" '
        'mask="16384" name="Group" sname="Group" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="Expanded" '
        'mask="4" name="Expanded" sname="Expanded" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="Title" '
        'mask="0" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_point" id="AutoCommit" '
        'mask="69632" name="AutoCommit" sname="AutoCommit" source="1" type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_point" group="Block Specific::" hierarchy="UGS::UICOMP_point" '
        'id="AutoProgress" mask="0" name="AutoProgress" sname="AutomaticProgression" source="1" '
        'type="logical" value="True"/>'
        '<Property AskForcedBits="0" AskRequiresSetting="0" ClassID="UGS::UICOMP_point" dynamic="1" '
        'group="Block Specific::" hierarchy="UGS::UICOMP_point" id="ToolbarToggleMask" mask="256" '
        'name="ToolbarToggleMask" sname="SnapPointTypesOnByDefault" source="2" type="bits" '
        'value="0x11ffc"/>'
        '<Property AskForcedBits="0" AskRequiresSetting="0" ClassID="UGS::UICOMP_point" dynamic="1" '
        'group="Block Specific::" hierarchy="UGS::UICOMP_point" id="SnapMask" mask="16640" '
        'name="SnapMask" sname="SnapPointTypesEnabled" source="1" type="bits" value="0x11ffc"/>'
        '<Property ClassID="UGS::UICOMP_point" group="Block Specific::" hierarchy="UGS::UICOMP_point" '
        'id="Point" mask="32772" name="Point" sname="Point" source="3" type="point" '
        'value="0.000000 0.000000 0.000000"/>'
        '<Property ClassID="UGS::UICOMP_point" group="Block Specific::" hierarchy="UGS::UICOMP_point" '
        'id="NoHandle" mask="69636" name="NoHandle" sname="NoHandle" source="1" type="logical" '
        'value="False"/>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title))


def _group_item(gid, title, children_xml, columns=1):
    """组容器(照抄主脚本 _group_item 的精简版, 单列)。"""
    return (
        '<item Expanded="True" class="UGS::UICOMP_group" hierarchy="" id="{id}" name="{id}" notes="" '
        'presentation="Group" type="uicomp"><PropertyList>'
        '<Property class="UGS::UI::Comp::Container" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_group" id="Members" mask="0" name="Members" sname="Members" source="1" '
        'type="array"><PropertyList Expanded="1" class="UGS::UI::Comp::Container" '
        'hierarchy="UGS::UICOMP_group" id="ContainerItems" mode="1">{children}</PropertyList></Property>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="API Name" '
        'mask="16400" name="API Name" sname="BlockID" source="3" type="string" value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Title" '
        'mask="1" name="Title" sname="Label" source="1" type="utfstring" value="{title}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Visibility" '
        'mask="0" name="Visibility" sname="Show" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Sensitivity" '
        'mask="0" name="Sensitivity" sname="Enable" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Group" '
        'mask="86020" name="Group" sname="Group" source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_group" group="Block Specific::" hierarchy="UGS::UICOMP_group" '
        'id="Column" mask="16384" name="Column" sname="Column" source="1" type="integer" value="{col}"/>'
        '</PropertyList></item>'
    ).format(id=gid, title=_esc(title), children=children_xml, col=columns)


def build_pick_dlx(part_name, index, total):
    """单件"指定点"对话框 XML: 标签说明 + 指定点控件; OK=确认, Cancel=中止。"""
    cue = ("【%d/%d】%s：点\"指定点\"框后在图形区拾取定位点(可捕捉), 点确定继续"
           % (index, total, part_name))
    tip = ("件: %s\n"
           "拾取后确定前请核对框内坐标数值, 点错重拾即可。\n"
           "【确定】=归零本件    【取消】=中止拾点(已确认的件仍会写回)"
           % part_name)
    grp = _group_item("grp_pick", "定位点",
                      _blk_label("lbl_tip", tip) + _blk_point("PT0", "定位点"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Dialog ContainerItems="1" Expanded="1" NX="2312.0.0" class="" id="Dialog" '
        'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
        'title="NX StdZeroRef" type="uicomp" version="1.0.0">'
        + grp +
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
        'value="标准件定位点归零"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
        'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
        'value="{cue}"/>'
        '<Property ClassID="UGS::UICOMP" brief="0" dynamic="0" group="General::Other::" '
        'hierarchy="UGS::Styler::DialogItem" id="NavigationStyle" mask="393472" '
        'name="NavigationStyle" selected="0" sname="Navigation Style" source="1" type="enum">'
        '<Option name="OK Cancel" value="0"/><Option name="Close" value="1"/>'
        '<Option name="OK Apply Cancel" value="2"/></Property>'
        '</PropertyList></Dialog>\n'
    ).format(cue=_esc(cue))


def _fresh_dlx_path(script_dir):
    """唯一毫秒戳 dlx 文件名(NX 按文件名回灌旧值, 重名会吃旧界面值)。
    script_dir = 本工具所在目录(tools), dlx 写到项目根的 logs/。"""
    logs = os.path.join(os.path.dirname(script_dir), "logs")
    d = logs if os.path.isdir(logs) else script_dir
    return os.path.join(d, "nx_zero_pick_%d.dlx" % int(time.time() * 1000))


def _as_xyz(v):
    """Point3d/序列 → (x,y,z); 不合法返回 None。"""
    try:
        x, y, z = float(v.X), float(v.Y), float(v.Z)
        if all(math.isfinite(t) for t in (x, y, z)):
            return (x, y, z)
    except Exception:
        pass
    try:
        if len(v) >= 3:
            t = (float(v[0]), float(v[1]), float(v[2]))
            if all(math.isfinite(q) for q in t):
                return t
    except Exception:
        pass
    return None


def _read_point(block):
    """点控件取值多通道梯: .Value → GetPoint("Point") → GetPoint("Value")。"""
    try:
        p = _as_xyz(block.Value)
        if p:
            return p, ".Value"
    except Exception:
        pass
    for name in ("Point", "Value"):
        props = None
        try:
            props = block.GetProperties()
            p = _as_xyz(props.GetPoint(name))
            if p:
                return p, "GetPoint(%s)" % name
        except Exception:
            pass
        finally:
            if props is not None:
                try:
                    props.Dispose()
                except Exception:
                    pass
    return None, None


def selftest():
    """无 NX 纯逻辑自测。"""
    n = [0]

    def ok(cond, msg):
        assert cond, "自测失败: %s" % msg
        n[0] += 1

    ok(parse_xyz("1,2,3") == (1.0, 2.0, 3.0), "基本解析")
    ok(parse_xyz(" 1.5 , -2 , 0 ") == (1.5, -2.0, 0.0), "带空格")
    for bad in ("1,2", "a,b,c", "1,2,3,4", ""):
        try:
            parse_xyz(bad)
            ok(False, "应拒绝 %r" % bad)
        except ValueError:
            ok(True, "拒绝 %r" % bad)

    a = parse_args(["--part", "接线盒", "--point", "1,2,3", "--dry-run"])
    ok(a.part == "接线盒" and a.point == "1,2,3" and a.dry_run, "参数解析")
    d = parse_args([])
    ok(d.part is None and d.point is None and not d.dry_run, "默认参数")
    d2 = parse_args(["--dry-run", "NX注水参数", "--foo"])
    ok(d2.dry_run, "忽略未知参数")

    ok(effective_argv(["nx_zero_ref.py"]) == [], "空 MANUAL_ARGS")
    ok(effective_argv(["nx_zero_ref.py", "--dry-run"]) == ["--dry-run"],
       "有 argv 不看 MANUAL_ARGS")
    global MANUAL_ARGS
    old = MANUAL_ARGS
    try:
        MANUAL_ARGS = "--dry-run --part 盒"
        ok(effective_argv(["x"]) == ["--dry-run", "--part", "盒"],
           "MANUAL_ARGS 生效")
    finally:
        MANUAL_ARGS = old

    ok(src_dir_of(__file__).endswith(SRC_DIRNAME), "源目录推导")
    ok(out_dir_of(__file__).endswith(OUT_DIRNAME), "输出目录推导")
    ok(out_dir_of(__file__, "custom").endswith("custom"), "输出目录覆盖")

    ok(delta_for(1, 2, 3) == (-1.0, -2.0, -3.0), "位移计算")
    ok(is_at_origin(0, 0, 0) and is_at_origin(1e-9, 0, 0), "原点判定")
    ok(not is_at_origin(0.001, 0, 0), "非原点判定")
    ok(fmt_point((1, 2, 3.5)) == "(1.000000, 2.000000, 3.500000)", "格式化")

    ok(_esc('a<b>&"c') == "a&lt;b&gt;&amp;&quot;c", "XML 转义")
    xml = build_pick_dlx("大水口-18.prt", 3, 14)
    ok('id="PT0"' in xml and "UICOMP_point" in xml, "dlx 含点控件")
    ok("大水口-18.prt" in xml and "NX StdZeroRef" in xml, "dlx 含件名/标题")
    ok('NavigationStyle' in xml and '<Option name="OK Cancel" value="0"/>' in xml,
       "dlx 导航样式")

    class _P3(object):
        X, Y, Z = 1.0, 2.0, 3.5
    ok(_as_xyz(_P3()) == (1.0, 2.0, 3.5), "Point3d 形取值")
    ok(_as_xyz([4, 5, 6]) == (4.0, 5.0, 6.0), "序列形取值")
    ok(_as_xyz("bad") is None, "垃圾值拒绝")

    here = os.path.dirname(os.path.abspath(__file__))
    tmp = os.path.join(here, "_selftest_tmp")
    os.makedirs(tmp, exist_ok=True)
    try:
        for fn in ("b.prt", "a.prt", "c.txt", "d.PRT"):
            with open(os.path.join(tmp, fn), "w", encoding="utf-8") as f:
                f.write("x")
        os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
        with open(os.path.join(tmp, "sub", "e.prt"), "w",
                  encoding="utf-8") as f:
            f.write("x")
        files = list_prt_files(tmp)
        ok(files == ["a.prt", "b.prt", "d.PRT"], "列表排序+过滤: %r" % files)
        ok(filter_files(files, None) == files, "不过滤")
        ok(filter_files(files, "A") == ["a.prt"], "子串过滤")
        ok(filter_files(files, "zzz") == [], "无命中")
        ok(out_path_for(tmp, "a.prt") == os.path.join(tmp, "a.prt"), "输出路径")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("nx_zero_ref 自测通过: %d 项" % n[0])


# ---------------------------------------------------------------------------
# NX 部分(import NXOpen 放在函数里, 保证 --selftest 无 NX 可跑)
# ---------------------------------------------------------------------------

def _log(session, msg):
    try:
        lw = session.ListingWindow
        if not lw.IsOpen:
            lw.Open()
        lw.WriteFullline(msg)
    except Exception:
        pass
    try:
        session.LogFile.WriteLine(msg)
    except Exception:
        pass


def is_batch(session):
    """NX 批处理会话判定; 属性/方法两种形态都兼容, 判不出按非批处理。"""
    try:
        v = session.IsBatch
        return bool(v() if callable(v) else v)
    except Exception:
        return False


def _msg(session, title, text, error=False):
    """弹窗; 批处理/失败时静默降级为日志。"""
    try:
        import NXOpen
        if is_batch(session):
            _log(session, "[弹窗] %s: %s" % (title, text))
            return
        NXOpen.UI.GetUI().NXMessageBox.Show(
            title,
            NXOpen.NXMessageBox.DialogType.Error if error
            else NXOpen.NXMessageBox.DialogType.Information,
            text)
    except Exception:
        _log(session, "[弹窗] %s: %s" % (title, text))


def _enum(root, paths, what):
    """按路径梯尝试解析枚举成员, 全部失败抛 RuntimeError。"""
    for path in paths:
        obj = root
        found = True
        for name in path:
            obj = getattr(obj, name, None)
            if obj is None:
                found = False
                break
        if found:
            return obj
    raise RuntimeError("找不到枚举: %s" % what)


class PickDialog(object):
    """单件"指定点"对话框: OK=读点返回, Cancel=中止拾点。
    (创建/回调/Launch 模式照抄主脚本 SelectionDialog, 含 Initialize/Shown
    两个处理器——上轮"初始化回调未注册"崩溃即因漏掉它们。)"""

    def __init__(self, nx, ui, dlx_path):
        self.nx = nx
        self.theUI = ui
        self.result = None        # ('ok',p)/('cancel',None)/('empty',None)/('error',msg)
        self.theDialog = ui.CreateDialog(dlx_path)
        self.theDialog.AddOkHandler(self.ok_cb)
        self.theDialog.AddCancelHandler(self.cancel_cb)
        self.theDialog.AddInitializeHandler(self.initialize_cb)
        try:
            self.theDialog.AddDialogShownHandler(self.shown_cb)
        except Exception:
            pass
        self.blocks = {}

    def initialize_cb(self):
        return 0

    def shown_cb(self):
        return 0

    def _find(self, bid):
        if bid not in self.blocks:
            b = self.theDialog.TopBlock.FindBlock(bid)
            if b is None:
                return None
            self.blocks[bid] = b
        return self.blocks[bid]

    def ok_cb(self):
        b = self._find("PT0")
        if b is None:
            self.result = ("error", "对话框里找不到点控件 PT0")
            return 0
        p, _ch = _read_point(b)
        if p is None:
            self.result = ("empty", None)
        else:
            self.result = ("ok", p)
        return 0

    def cancel_cb(self):
        self.result = ("cancel", None)
        return 0

    def Launch(self):
        try:
            self.theDialog.Launch()
        except Exception as ex:
            self.result = ("error", "对话框启动失败: %s" % ex)
        return self.result

    def Dispose(self):
        if getattr(self, "theDialog", None) is not None:
            try:
                self.theDialog.Dispose()
            except Exception:
                pass
            self.theDialog = None


def pick_point_dialog(nx, ui, part_name, index, total, script_dir):
    """弹一次点选对话框。返回 ('ok',p) / ('cancel',None) / ('empty',None) /
    ('error',msg)。"""
    dlx = _fresh_dlx_path(script_dir)
    try:
        with io.open(dlx, "w", encoding="utf-8") as f:
            f.write(build_pick_dlx(part_name, index, total))
    except Exception as ex:
        return ("error", "生成对话框文件失败: %s" % ex)
    dial = PickDialog(nx, ui, dlx)
    try:
        r = dial.Launch()
    finally:
        dial.Dispose()
        try:
            os.remove(dlx)
        except Exception:
            pass
    return r


def _normkey(path):
    return os.path.normcase(os.path.normpath(path))


def _find_open_part(session, path):
    """会话里找已加载的同一部件: 全路径相同→返回它; 同名不同路径→报冲突。"""
    try:
        parts = list(session.Parts)
    except Exception:
        return None, None
    key = _normkey(path)
    base = os.path.basename(path)
    for part in parts:
        try:
            fp = part.FullPath
        except Exception:
            continue
        if not fp:
            continue
        if _normkey(fp) == key:
            return part, None
        if os.path.basename(fp) == base:
            return None, ("会话里已有同名但不同路径的部件:\n  已加载: %s\n  要打开: %s\n"
                          "请先关闭其一再试。" % (fp, path))
    return None, None


def _activate(session, ufs, part):
    """设为显示+工作部件; 各自失败仅记录不中断。"""
    try:
        session.Parts.SetDisplay(part)
    except Exception:
        try:
            ufs.Part.SetDisplayPart(part.Tag)
        except Exception as ex:
            _log(session, "  设为显示部件失败(忽略): %s" % ex)
    try:
        session.Parts.SetWork(part)
        return
    except Exception as ex:
        _log(session, "  SetWork 失败, 改试 UF: %s" % ex)
    try:
        ufs.Assem.SetWorkPart(part.Tag)
    except Exception as ex:
        _log(session, "  UF SetWorkPart 失败(忽略): %s" % ex)


def open_part(session, ufs, path):
    """打开部件并设为显示/工作部件; 已加载的直接复用; 三条通道逐级尝试。"""
    part, conflict = _find_open_part(session, path)
    if conflict:
        raise RuntimeError(conflict)
    if part is not None:
        _activate(session, ufs, part)
        _log(session, "  (会话中已加载, 直接复用)")
        return part
    for method_name in ("OpenBasePart", "OpenDisplay"):
        method = getattr(session.Parts, method_name, None)
        if method is None:
            continue
        try:
            ret = method(path)
        except Exception:
            continue
        p = ret[0] if isinstance(ret, tuple) else ret
        if p is None:
            continue
        if isinstance(ret, tuple) and len(ret) > 1 and ret[1] is not None:
            try:
                ret[1].Dispose()
            except Exception:
                pass
        _activate(session, ufs, p)
        _log(session, "  (经 Parts.%s 打开)" % method_name)
        return p
    ret = ufs.Part.Open(path)
    tag = ret[0] if isinstance(ret, tuple) else ret
    try:
        ufs.Part.SetDisplayPart(tag)
    except Exception:
        pass
    p = session.Parts.Display
    if p is None:
        raise RuntimeError("UF 打开后拿不到显示部件对象")
    _activate(session, ufs, p)
    _log(session, "  (经 UF Part.Open 打开)")
    return p


def close_part(session, ufs, part):
    """关闭部件: NXOpen 路线失败则退 UF 路线; 全失败仅日志。"""
    if part is None:
        return
    try:
        import NXOpen
        tree = _enum(NXOpen,
                     [("BasePart", "CloseWholeTree", "False_"),
                      ("BasePart", "CloseWholeTree", "False")],
                     "CloseWholeTree.False")
        modified = _enum(NXOpen,
                         [("BasePart", "CloseModified", "CloseModified")],
                         "CloseModified")
        part.Close(tree, modified, None)
        return
    except Exception:
        pass
    try:
        ufs.Part.Close(part.Tag, 1, 1)
    except Exception as ex:
        _log(session, "关闭部件失败(忽略): %s" % ex)


# ---- 预览副本(全部走主脚本已验证的 AddComponent→提升→删组件 三件套) ----

def _import_runner(script_dir):
    """导入主脚本模块(位于项目根), 复用其选择对话框/放置三件套。"""
    root = os.path.dirname(script_dir)
    if root not in sys.path:
        sys.path.insert(0, root)
    import nx_extrude_runner as runner
    return runner


def _add_component(session, runner, work_part, path, name, pos, refset):
    """以恒等姿态在 pos 放置组件(指定引用集; 含 TypeError 梯)。"""
    import NXOpen
    ca = work_part.ComponentAssembly
    m3 = runner._matrix3x3(NXOpen, False)
    try:
        comp, _ls = ca.AddComponent(path, refset, name, pos, m3, -1)
    except TypeError:
        comp = ca.AddComponent(path, refset, name, pos, m3, -1, False)
    return comp


def _delete_objects(session, objs, mark_name):
    """UpdateManager 删除对象(主脚本删组件同款)。"""
    import NXOpen
    try:
        session.UpdateManager.AddToDeleteList(objs)
        session.UpdateManager.DoUpdate(
            session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                mark_name))
        return True
    except Exception:
        return False


def _name_bodies(bodies, stem):
    for i, b in enumerate(bodies, 1):
        try:
            b.Name = "%s%s#%d" % (GROUP_PREFIX, stem, i)
        except Exception:
            pass


def _make_group(session, ufs, bodies, name):
    """已停用: UF 分组接口参数对不上, 标识用体名(ZERO_件名#序号)即可。"""
    return False


def _move_bodies_to_layer(session, work_part, bodies):
    """副本实体统一搬到第 1 层(保留原 prt 图层号会在当前部件里被隐藏,
    看起来像"缺实体")。同时把原图层分布打进日志。"""
    seen = {}
    moved = 0
    for b in bodies:
        try:
            seen[b.Layer] = seen.get(b.Layer, 0) + 1
        except Exception:
            pass
        done = False
        try:
            work_part.Layers.MoveDisplayableObjectToLayer(b, 1)
            done = True
        except Exception:
            try:
                b.Layer = 1
                done = True
            except Exception:
                pass
        if done:
            moved += 1
    _log(session, "  副本原图层分布 %s → 统一移到第 1 层(%d/%d)。"
         % (seen or "?", moved, len(bodies)))


def _hide_component(session, comp):
    """隐藏组件壳(不删除——删壳可能连带破坏关联提升体, 那是"加载完成后
    缺斤少两"的根因)。清理阶段统一删除。"""
    try:
        import NXOpen
        comp.Visibility = NXOpen.Assemblies.ComponentVisibilityFlag.Hidden
        return True
    except Exception:
        pass
    try:
        comp.Suppress()
        return True
    except Exception as ex:
        _log(session, "  组件壳隐藏失败(壳仍显示, 不影响定位): %s" % ex)
        return False


def promote_copy(session, runner, part, ufs, src_path, name, pos, feat_name):
    """组件放置(Entire Part→MODEL 逐个尝试并核对副本实体数齐全)+提升。
    返回 (bodies, comp, complete)。组件壳交调用方处理(隐藏/删除)。"""
    import NXOpen
    best = None
    for refset in ("Entire Part", "MODEL"):
        comp = _add_component(session, runner, part, src_path, name,
                              pos, refset)
        try:
            proto_n = len(list(comp.Prototype.Bodies))
        except Exception:
            proto_n = -1
        bodies = runner._promote_body(
            part, comp, feat_name, lambda m: _log(session, "  " + m),
            body_index=None)
        bodies = [b for b in (bodies or []) if b is not None]
        _log(session, "  引用集 %s: 件内 %s 实体 → 副本 %d 个。"
             % (refset, proto_n if proto_n >= 0 else "?", len(bodies)))
        if bodies and proto_n >= 0 and len(bodies) >= proto_n:
            if best is not None:
                _delete_objects(session, best[0], "归零 删较差副本")
                _delete_objects(session, [best[1]], "归零 删较差组件壳")
            return bodies, comp, True
        if best is None or len(bodies) > len(best[0]):
            if best is not None:
                _delete_objects(session, best[0], "归零 删较差副本")
                _delete_objects(session, [best[1]], "归零 删较差组件壳")
            best = (bodies, comp)
        elif bodies:
            _delete_objects(session, bodies, "归零 删较差副本")
            _delete_objects(session, [comp], "归零 删较差组件壳")
    if best is None:
        return [], None, False
    return best[0], best[1], False


def load_preview_copy(session, runner, work_part, ufs, path, stem,
                      pos=(0.0, 0.0, 0.0)):
    """把 prt 实体提升复制进当前工作部件(真实几何, 捕捉必然可用),
    立即移除参数成哑实体(与组件壳彻底脱钩)。返回 (bodies, comp, complete)。"""
    name = "%s%s" % (GROUP_PREFIX, stem)
    bodies, comp, complete = promote_copy(
        session, runner, work_part, ufs, path, name,
        NXOpen_Point3d(pos), "%s%s" % (FEAT_PREFIX, stem))
    if bodies:
        _name_bodies(bodies, stem)
        _move_bodies_to_layer(session, work_part, bodies)
        runner._remove_parameters(session, work_part, bodies,
                                  lambda m: _log(session, "  " + m))
        _hide_component(session, comp)   # 已去参数化, 隐藏壳防叠显
    return bodies, comp, complete


def NXOpen_Point3d(pos):
    import NXOpen
    return NXOpen.Point3d(*pos)


def replace_preview_at(session, runner, work_part, ufs, path, stem,
                       old_bodies, old_comp, p):
    """把该件副本"平移"到 −p: 删旧副本与旧壳 → 在 −p 处重新加载提升。"""
    if old_bodies:
        _delete_objects(session, old_bodies, "归零 删旧副本")
    if old_comp is not None:
        _delete_objects(session, [old_comp], "归零 删旧组件壳")
    bodies, comp, complete = load_preview_copy(
        session, runner, work_part, ufs, path, stem,
        pos=(-p[0], -p[1], -p[2]))
    _log(session, "  副本已就位: 定位点 %s → 原点(位移 %s)%s"
         % (fmt_point(p), fmt_point(delta_for(*p)),
            "" if complete else " [注意: 该件副本实体可能不齐全]"))
    return bodies, comp


def cleanup_preview(session, previews):
    """删除全部预览副本实体与组件壳。"""
    bodies = []
    comps = []
    for e in previews:
        bodies.extend([b for b in e[2] if b is not None])
        if e[3] is not None:
            comps.append(e[3])
    if bodies and _delete_objects(session, bodies, "归零 清理预览副本"):
        _log(session, "已清理当前部件中的 %d 个副本实体。" % len(bodies))
    elif bodies:
        _log(session, "副本清理失败(可手动删除 ZERO_ 实体/Ctrl+Z)。")
    if comps:
        _delete_objects(session, comps, "归零 清理组件壳")


def model_template_path():
    """NX"模型"模板路径(mm)。"""
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


def write_back_one(session, ufs, runner, src_path, out_path, p,
                   dry_run, index, total):
    """写回单件(不经移动 API): 新建输出部件 → 原件以组件放在 −定位点 →
    提升独立体 → 移除参数成哑实体 → 删组件壳 → 保存。原始 prt 全程不动。"""
    import NXOpen
    fname = os.path.basename(src_path)
    stem = os.path.splitext(fname)[0]
    head = "[%d/%d] %s" % (index, total, fname)
    px, py, pz = p
    if dry_run:
        _log(session, "%s [dry-run] 位移: %s"
             % (head, fmt_point(delta_for(px, py, pz))))
        return "ok"
    _log(session, "%s 生成归零副本..." % head)
    # 部件内部名不能与原件相同(同名组件放置会被 NX 当成循环装配),
    # 用毫秒戳临时名; 且从"模型"模板复制而来, 输出件打开时直接进入建模。
    out_dir_n = os.path.dirname(out_path)
    tmpl = model_template_path()
    tmp = os.path.join(out_dir_n, "_staging_%d.prt" % int(time.time() * 1000))
    if os.path.isfile(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    op, _cf = _find_open_part(session, tmp)
    if op is not None:
        close_part(session, ufs, op)
    try:
        import shutil
        if tmpl:
            shutil.copyfile(tmpl, tmp)
            _log(session, "  基础: 模型模板(建模应用已内置)")
        else:
            _log(session, "  提示: 找不到模型模板, 输出件打开时需手动进入建模。")
            ufs.Part.New(tmp, 1)           # 1 = mm
    except Exception as ex:
        raise RuntimeError("创建输出部件失败: %s" % ex)
    ret = ufs.Part.Open(tmp)
    tag = ret[0] if isinstance(ret, tuple) else ret
    try:
        ufs.Part.SetDisplayPart(tag)
    except Exception:
        pass
    part = session.Parts.Display
    if part is None:
        raise RuntimeError("新建输出部件失败: %s" % tmp)
    try:
        session.Parts.SetWork(part)
    except Exception:
        try:
            ufs.Assem.SetWorkPart(tag)
        except Exception:
            pass
    # 切到建模应用, 让输出件打开时直接进入建模(与原件行为一致)
    for app in ("UG_APP_MODELING", "MODELING"):
        try:
            session.ApplicationSwitchImmediate(app)
            break
        except Exception:
            pass
    bodies, comp, complete = promote_copy(
        session, runner, part, ufs, src_path,
        "%s%s" % (GROUP_PREFIX, stem), NXOpen.Point3d(-px, -py, -pz),
        "%s%s" % (FEAT_PREFIX, stem))
    if not bodies:
        raise RuntimeError("输出部件里没有提升出实体")
    runner._remove_parameters(session, part, bodies,
                              lambda m: _log(session, "  " + m))
    _delete_objects(session, [comp], "归零 删组件壳")
    # SaveAs 到最终名会被 NX 拒绝(会话里已加载的原件与其内部名同名)——
    # 改走: 存临时名 → 关部件 → 磁盘改名。
    try:
        ufs.Part.Save()                        # 无参形式, 保存当前工作部件
    except Exception:
        sc = getattr(NXOpen.BasePart.SaveComponents, "True_",
                     getattr(NXOpen.BasePart.SaveComponents, "True", None))
        ca_ = getattr(NXOpen.BasePart.CloseAfterSave, "False_",
                      getattr(NXOpen.BasePart.CloseAfterSave, "False", None))
        part.Save(sc, ca_)
    try:
        ufs.Part.Close(tag, 1, 1)
    except Exception:
        pass
    try:
        os.replace(tmp, out_path)
    except OSError as ex:
        raise RuntimeError("改名 %s → %s 失败: %s" % (tmp, out_path, ex))
    try:
        for n in os.listdir(out_dir_n):
            if n.startswith("_staging_") and n.endswith(".prt"):
                os.remove(os.path.join(out_dir_n, n))
    except OSError:
        pass
    _log(session, "%s 已保存: %s (实体 %d 个, 位移 %s)"
         % (head, os.path.basename(out_path), len(bodies),
            fmt_point(delta_for(px, py, pz))))
    return "ok"
    _log(session, "%s 已保存: %s (实体 %d 个, 位移 %s)"
         % (head, os.path.basename(out_path), len(bodies),
            fmt_point(delta_for(px, py, pz))))
    return "ok"


def close_loaded_src_parts(session, ufs, src_dir, files):
    """关闭会话中已加载的标准件源部件。归零副本与原件文件名相同, 原件
    不关的话, 打开副本会报"已加载另一版本的部件"(NX 不允许同名部件并存)。"""
    closed = 0
    for fname in files:
        part, _cf = _find_open_part(session, os.path.join(src_dir, fname))
        if part is not None:
            try:
                close_part(session, ufs, part)
                closed += 1
            except Exception:
                pass
    if closed:
        _log(session, "已关闭 %d 个已加载的标准件源部件(避免与归零件同名冲突)。"
             % closed)


def _new_temp_preview_part(session, ufs, script_dir):
    """建一个用完即弃的预览临时部件并设为显示/工作部件。
    预览不落在用户打开的部件里(NX 关窗口≠关部件, 会在退出时残留
    "未保存更改")。失败返回 None。"""
    d = os.path.join(script_dir, "logs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = script_dir
    path = os.path.join(d, "_preview_%d.prt" % int(time.time() * 1000))
    try:
        ret = ufs.Part.New(path, 1)            # 1 = mm
        tag = ret[0] if isinstance(ret, tuple) else ret
    except Exception as ex:
        _log(session, "创建预览临时部件失败: %s" % ex)
        return None
    try:
        ufs.Part.SetDisplayPart(tag)
    except Exception:
        pass
    part = session.Parts.Display
    if part is None:
        _log(session, "创建预览临时部件失败: 拿不到显示部件")
        return None
    try:
        session.Parts.SetWork(part)
    except Exception:
        try:
            ufs.Assem.SetWorkPart(tag)
        except Exception:
            pass
    _PREVIEW_PART["part"] = part
    _PREVIEW_PART["path"] = path
    return part


def _discard_preview(session, ufs):
    """丢弃预览临时部件(不保存——里面只有预览副本), 清理占位文件。"""
    part = _PREVIEW_PART.get("part")
    path = _PREVIEW_PART.get("path")
    _PREVIEW_PART["part"] = None
    _PREVIEW_PART["path"] = None
    if part is not None:
        try:
            close_part(session, ufs, part)     # CloseModified=丢弃更改
        except Exception:
            pass
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def select_parts(session, runner, files, script_dir):
    """复用主脚本标准件选择框; 返回选中文件名列表, 取消返回 None。默认全不选。"""
    dlx = runner._fresh_dlx_path("nx_std_select")   # 与主脚本窗口①同名基名
    with io.open(dlx, "w", encoding="utf-8") as f:
        f.write(runner.build_selection_dlx(files, []))   # 默认全不选
    dlg = runner.SelectionDialog(dlx, files, [])
    try:
        r = dlg.Launch()
    finally:
        dlg.Dispose()
        try:
            os.remove(dlx)
        except Exception:
            pass
    return r


def run(session, ufs, opts, script_file):
    import NXOpen
    script_dir = os.path.dirname(os.path.abspath(script_file))
    src_dir = src_dir_of(script_file)
    out_dir = out_dir_of(script_file, opts.out)
    files = filter_files(list_prt_files(src_dir), opts.part)

    if not os.path.isdir(src_dir):
        _msg(session, "归零工具", "找不到标准件目录:\n%s" % src_dir, error=True)
        return 1
    if not files:
        _msg(session, "归零工具",
             "没有匹配的标准件 .prt 文件:\n目录: %s\n过滤: %s"
             % (src_dir, opts.part or "(无)"), error=True)
        return 1

    try:
        runner = _import_runner(script_dir)
    except Exception as ex:
        _msg(session, "归零工具",
             "无法导入主脚本 nx_extrude_runner(需要复用其提升/移除参数实现):\n%s" % ex,
             error=True)
        return 1

    # ---- 单件测量数据式(--point + --part): 跳过全部 UI, 直接写回 ----
    if opts.point:
        try:
            p = parse_xyz(opts.point)
        except ValueError as ex:
            _msg(session, "归零工具", "--point 参数错误: %s" % ex, error=True)
            return 1
        if len(files) > 1:
            _log(session, "警告: --point 对 %d 个文件都用同一个点" % len(files))
        if not opts.dry_run and not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        stats = {"ok": 0, "fail": 0}
        for i, fname in enumerate(files, 1):
            try:
                r = write_back_one(session, ufs, runner,
                                   os.path.join(src_dir, fname),
                                   out_path_for(out_dir, fname), p,
                                   opts.dry_run, i, len(files))
                stats[r] += 1
            except Exception as ex:
                stats["fail"] += 1
                _log(session, "[%d/%d] %s 失败: %s" % (i, len(files), fname, ex))
        _log(session, "处理结束: 成功 %d, 失败 %d。输出目录: %s"
             % (stats["ok"], stats["fail"], out_dir))
        close_loaded_src_parts(session, ufs, src_dir, files)
        return 0 if stats["fail"] == 0 else 2

    # ---- 完整点选流程 ----
    # 预览放在工具自建的临时部件里: 所见即所得, 结束时整体丢弃,
    # 不会弄脏你打开的任何部件(旧版在"当前页面"上操作, 退出时残留
    # "未保存更改"提示即此因)。
    work_part = _new_temp_preview_part(session, ufs, script_dir)
    if work_part is None:
        _msg(session, "归零工具", "创建预览临时部件失败。", error=True)
        return 1

    picked = select_parts(session, runner, files, script_dir)
    if picked is None:
        _log(session, "用户在选择窗口取消, 退出。")
        return 0
    if not picked:
        _msg(session, "归零工具", "未勾选任何标准件。", error=True)
        return 1

    _log(session, "========== 标准件定位点归零 v%s ==========" % SCRIPT_VERSION)
    _log(session, "选中 %d 件: %s" % (len(picked), ", ".join(picked)))

    # 阶段2: 加载预览副本(整件组件)
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        "归零-加载预览副本")
    previews = []          # [[fname, stem, bodies, comp], ...]
    load_fail = []
    incomplete = []
    for i, fname in enumerate(picked, 1):
        stem = os.path.splitext(fname)[0]
        try:
            bodies, comp, complete = load_preview_copy(
                session, runner, work_part, ufs,
                os.path.join(src_dir, fname), stem)
        except Exception as ex:
            load_fail.append(fname)
            _log(session, "[%d/%d] %s 加载失败: %s" % (i, len(picked), fname, ex))
            continue
        if not bodies:
            load_fail.append(fname)
            _log(session, "[%d/%d] %s 内没有实体, 跳过。" % (i, len(picked), fname))
            continue
        previews.append([fname, stem, bodies, comp])
        if not complete:
            incomplete.append(fname)
            _log(session, "[%d/%d] %s 警告: 副本实体不齐全, 该件定位可能不准!"
                 % (i, len(picked), fname))
        else:
            _log(session, "[%d/%d] %s 已加载副本(实体齐全)。"
                 % (i, len(picked), fname))
    if not previews:
        _msg(session, "归零工具", "没有任何一件加载成功, 退出。", error=True)
        return 1

    # 阶段3: 逐件拾取定位点并当场归位
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        "归零-逐件定位")
    try:
        ui = NXOpen.UI.GetUI()
    except Exception:
        ui = None
    if ui is None or is_batch(session):
        _msg(session, "归零工具",
             "当前环境无法弹出点选对话框(无界面批处理会话)。\n"
             "请在 NX 图形界面用 工具→日记→播放 运行。",
             error=True)
        cleanup_preview(session, previews)
        return 1

    collected = {}         # fname → (px,py,pz)
    abort = False
    for i, entry in enumerate(previews, 1):
        fname, stem, bodies, comp = entry[0], entry[1], entry[2], entry[3]
        while True:
            act, payload = pick_point_dialog(NXOpen, ui, fname, i,
                                             len(previews), script_dir)
            if act == "cancel":
                _log(session, "[%d/%d] %s 用户中止拾点。" % (i, len(previews), fname))
                abort = True
                break
            if act == "empty":
                _log(session, "[%d/%d] %s 未拾取到点, 请重试。" % (i, len(previews), fname))
                continue
            if act == "error":
                _log(session, "[%d/%d] %s 点选失败: %s" % (i, len(previews), fname, payload))
                abort = True
                break
            p = payload
            _log(session, "[%d/%d] %s 定位点: %s" % (i, len(previews), fname,
                                                     fmt_point(p)))
            collected[fname] = p
            entry[2], entry[3] = replace_preview_at(
                session, runner, work_part, ufs,
                os.path.join(src_dir, fname), stem, bodies, comp, p)
            break
        if abort:
            break

    # 阶段4: 清理预览副本与组件壳(先清再写回, 避免 SaveAs 改名时引用混乱)
    cleanup_preview(session, previews)

    # 阶段5: 写回文件
    results = []
    if collected:
        if not opts.dry_run and not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        _log(session, "---- 写回 %d 件 ----" % len(collected))
        for i, fname in enumerate(sorted(collected), 1):
            try:
                write_back_one(session, ufs, runner,
                               os.path.join(src_dir, fname),
                               out_path_for(out_dir, fname), collected[fname],
                               opts.dry_run, i, len(collected))
                results.append((fname, "成功"))
            except Exception as ex:
                results.append((fname, "失败: %s" % ex))
                _log(session, "写回 %s 失败: %s" % (fname, ex))
    else:
        _log(session, "没有确认任何定位点, 不写回文件。")

    # 收尾: 关闭会话中已加载的标准件源部件(副本与原件同名, 不关会撞名)
    close_loaded_src_parts(session, ufs, src_dir, picked)

    lines = ["==== 归零汇总 ===="]
    for fname, stem, _b, _c in previews:
        if fname in collected:
            lines.append("  %s  位移 %s  [%s]"
                         % (fname, fmt_point(delta_for(*collected[fname])),
                            dict(results).get(fname, "未写回")))
        else:
            lines.append("  %s  未定位(中止)" % fname)
    if incomplete:
        lines.append("  副本实体不齐全(定位前请留意): %s" % ", ".join(incomplete))
    if load_fail:
        lines.append("  加载失败: %s" % ", ".join(load_fail))
    lines.append("输出目录: %s%s" % (out_dir,
                                     " [dry-run 未另存]" if opts.dry_run else ""))
    summary = "\n".join(lines)
    _log(session, summary)
    _msg(session, "归零工具", summary, error=any("失败" in r for _f, r in results))
    return 0


def main():
    argv = effective_argv(sys.argv)
    if "--selftest" in argv:
        selftest()
        return 0
    opts = parse_args(argv)

    try:
        import NXOpen
        import NXOpen.UF  # noqa: F401
    except ImportError:
        print("本工具需要在 NX 中运行(工具→日记→播放), 或用 --selftest 做无 NX 自测。")
        return 1

    session = ufs = None
    try:
        session = NXOpen.Session.GetSession()
        ufs = NXOpen.UF.UFSession.GetUFSession()
        script_file = os.path.abspath(sys.argv[0])
        return run(session, ufs, opts, script_file)
    except Exception:
        # 异常绝不让日记悄悄死掉: 全文进信息窗口 + 弹窗显示末段
        import traceback
        tb = traceback.format_exc()
        try:
            s2 = NXOpen.Session.GetSession()
            _log(s2, "归零工具异常退出:\n" + tb)
            _msg(s2, "归零工具-异常", tb[-1200:], error=True)
        except Exception:
            print(tb)
        return 3
    finally:
        # 预览临时部件用完即弃(不保存), 不给退出留"未保存更改"
        if ufs is not None:
            _discard_preview(session or NXOpen.Session.GetSession(), ufs)


if __name__ == "__main__":
    main()
