#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""probe_nx_compat.py — NX 版本兼容性运行时探针 v2.0
====================================================================
用途: 在目标 NX 实机(本次锁定 10/12)上一次性探明 nx_extrude_runner.py
兼容改造所需的全部"需要验证"项, 输出结构化清单, 不修改任何部件/配置。

v2.2 修订(据 NX10/NX12 实机 v2.1 结果):
  - v2.1 两遍二分命中根因: API006 变 AVAILABLE, API020 给出配方 =
    AddToSection([rule], NXObject.Null, NXObject.Null, NXObject.Null, Point3d,
    Mode.Create, False)。即旧版要求 seed/两 connector 传类型化 NXObject.Null 而非
    裸 None; rules 用 list、helpPoint 用 Point3d、mode 用枚举、7 参均正确。runner
    已据此加 _add_to_section_compat(先 None 后 Null, 2312 零回归)。
  - 新暴露第二障碍: API010/011 MISSING 因 ScRuleFactory.CreateRuleOptions 在
    NX10/12 不存在(AttributeError)。runner 已加 _sc_rule_options 可选化(旧版走
    无 opts 单参 CreateRuleFaceDumb/CreateRuleOuterEdgesOfFaces)。本版探针同步
    守卫 CreateRuleOptions, 使下轮能真正验证 EdgeBlend 全属性/AddChainset 与
    DeleteFace 在旧版是否可用; 并新增 API025 dump CreateRuleOuterEdgesOfFaces 签名。
  - MAR001~004 全 list=OK → SetTargetBodies/ReplaceRules/NewMassProperties/
    DisplayApply 收 Python list 无碍, NETarr=FAIL 仅因无 System(不致命)。
  - v2.1 修订(据 NX10/NX12 实机 v2.0 结果 —— 重大方向纠偏):
  - 实机证明 NX10(3.3.2)/NX12(3.6.1) 的 NXOpen.pyd 是 Siemens 自研 CPython C 扩展
    绑定, 非 pythonnet: API019 显示 'No module named System'、对象无 GetType、
    SelectionIntentRule 无 .array() —— 故 v2.0 的"反射签名 + .NET 数组"路线在这
    两版物理上无法构造, 反射自省全 reflect_err。
  - 且 list|tuple × enum|int × NoneSeed|CurveSeed × 6|7 参 16 组合全败, 而真实
    NX10/12 录制日志用的正是 Python list, 判定卡点在未枚举维度 → 本版:
      * 新增 API021~024: 抓绑定自带 __doc__/overloads/inspect.signature(自研绑定
        无反射时这是真实可接受类型的权威来源); 并对照 dump 一个收 list 成功的方法
        (CreateRuleBaseCurveDumb) 以揭示数组参数约定差异。
      * S3 二分补 helpPoint 形态轴(Point3d/tuple3/list3/None) 与 rules 单对象/
        SelectionIntentRule 包装轴; 成功配方含 HP 形态写入 _GOOD。
      * 修 probe 自身 bug: DisplayModification 在 session 上非 part(MAR004 之前
        part.DisplayManager AttributeError)。
  - 若本版 S3 仍全败, API021 的 __doc__ 将直接给出该版 AddToSection 真实签名,
    据此定 runner 通道或转 OpenUF 兜底(plan B)。
  - v2.0 (核心: 从"猜签名梯"改为"让机器自报 + 单维二分"):
  - 修复 v1.2/v1.3 致命 bug: _extrude_chain_probe 内引用未定义的 mode 变量
    (mode=nx.Section.Mode.Create 只在另一函数 _addtosection_introspect 里),
    导致除"7参list+intMode"外所有变体一跑即 NameError —— 探针实际不可用,
    且 NX10logs/NX12logs 系 v1.1 旧结果, NETArray 等关键变体从未在实机验证。
  - S3 AddToSection 改为: 先用 System.Reflection 打印该版本真实托管签名
    (API019), 再以 (rules载体 × mode枚举/整型 × seed None/曲线 × 元数7/6)
    逐轴二分, 首个成功即把可用配方写入全局 _GOOD, 供 _extrude_rect 与
    runner 复用 —— 一次跑完即可定位是 list、枚举、seed 还是元数挡的路。
  - 新增 MAR 组: 对 runner 里其余"传 Python list 给 .NET 数组参数"的调用点
    (SetTargetBodies/ReplaceRules/NewMassProperties/DisplayApply) 逐一实测
    "list 可用 vs 需 .NET 数组", 精确框定 runner _na() shim 覆盖面;
    布尔特征 CreateUnite/SubtractFeature 仅反射 dump 签名(不建特征免污染几何)。
  - 新增 API020: 直接输出"runner 照此写"的 AddToSection 配方(载体/枚举/seed/元数/
    rules 元素类型), 阶段 3 据此写薄 shim, 无需再猜。
  - v1.2 及更早(据 NX10/NX12 实机): dlx 两变体均可载(硬编造版本戳非必需),
    回调方法名与 2312 一致, CreateArc 向量版可用, CreateRuleBaseCurveDumb/
    CreateSection+OnlyCurves/Promotion/RemoveParameters/Display/LayerCategories/
    AddComponent(6参) 均 AVAILABLE; 唯一核心断点收敛到 S3 AddToSection 编组。
  - S3 AddToSection 升级为签名梯: 官方文档确认 NX10~2312 签名一致
    (rules, seed, startConnector, endConnector, helpPoint, mode[, bool]),
    故 2312 式调用在旧版 TypeError 必为绑定层类型编组问题 —— 梯子依次
    变换 seed=None→首曲线 / Python list→.NET 数组(若 bridge 支持), 一次
    跑完即定位可用通道; 全部失败时汇总每梯异常
  - 新增 VER004(UGII_BASE_DIR) / VER005(NXOpen.__file__ 路径解析版本):
    NX12 实机 UGII_ROOT_DIR 为残留 NX10 旧值, 环境变量探测不可靠,
    NXOpen 模块自身路径是唯一必然指向运行中 NX 的版本通道
  - API017 ERROR 时附加判读: "出自更新版本/不是部件文件" = stdparts 为
    NX2312 格式, 需在 NX2312 中设旧版兼容后重新另存(交付侧动作)
  - v1.1 修订(据 NX10 实机 v1.0): 拉伸主链分步探测 / Feature.Null 与
    AddToSection、CreateDirection 回退通道 / 矩阵三候选 / UI 部件上下文
    兜底 / 修复 API004-005 重复记录

运行方式(任选其一):
  1) NX 内: 菜单 工具 → 日记(Journal) → 播放, 选择本文件(推荐, UI 组有效)
  2) 批量:  <NX安装目录>\\NXBIN\\run_journal.exe probe_nx_compat.py
     (UI 组可能因无图形界面报错, 结果标注 ERROR 时请在方式1下复跑)
  3) 裸外部 Python(无 NX): 仅 PY 组照跑, API/UI/VER 组自动 SKIP —— 用于脚本自检

输出: logs\\nx_compat_probe.json  (机器可读)
      logs\\nx_compat_probe.csv   (Excel 友好, UTF-8 BOM)
每项字段: id / category / item / result / detail
  result ∈ AVAILABLE(可用) / MISSING(缺失) / ERROR(异常) / SKIP(未测) / INFO(信息)
  API/UI 组单项判定口径: 只要"核心 API 存在且基本调用成功"即 AVAILABLE,
  更进一步的完整提交(Commit)结果写在 detail 中, 不降低主判定。

设计原则:
  - 逐项 try/except 隔离, 单项失败绝不中断其余检查
  - 全部几何检查在新建临时 Part 内进行, 结束不保存
  - 不 import nx_extrude_runner, 完全自包含
  - dlx 模板逐字复用主脚本 build_selection_dlx/_group_item/_blk_enum 结构
    (NX2312 实证可用), 仅 NX= 属性按变体开关增删
  - 全脚本无 f-string/pathlib, Python 3.3.2(NX10) 即可运行
"""

import io
import json
import os
import sys

PROBE_VERSION = "2.2"
TEMP_PART_NAME = "nx_compat_probe"
ENUM_BLOCK_ID = "probe_enum"
ENUM_LABELS = ["甲", "乙"]

RESULTS = []


def add(rid, category, item, result, detail=""):
    RESULTS.append({"id": rid, "category": category, "item": item,
                    "result": result, "detail": str(detail) if detail else ""})
    print("[%s] %s %s: %s%s" % (rid, category, item, result,
                                (" | " + str(detail)) if detail else ""))


def script_dir():
    """项目根(本探针在 tools 目录内, stdparts/logs 均相对根)。"""
    try:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        return os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))


def out_dir():
    """输出目录: 脚本旁 logs/ 失败则 TEMP。"""
    d = os.path.join(script_dir(), "logs")
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
        return d
    except Exception:
        pass
    d = os.path.join(os.environ.get("TEMP") or script_dir(), "nx_compat_probe")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


# ---------------------------------------------------------------------------
# PY 组: 解释器能力(与 NX 无关, 任何 Python 都跑)
# ---------------------------------------------------------------------------

def probe_py():
    add("PY001", "PY", "解释器版本", "INFO", sys.version.replace("\n", " "))

    try:
        import importlib.util
        ok = hasattr(importlib.util, "spec_from_file_location") and \
            hasattr(importlib.util, "module_from_spec")
        add("PY002", "PY", "importlib.util.spec_from_file_location (>=3.4)",
            "AVAILABLE" if ok else "MISSING",
            "" if ok else "NX10 需配置加载三梯 shim")
    except Exception as ex:
        add("PY002", "PY", "importlib.util.spec_from_file_location (>=3.4)",
            "MISSING", "%s: %s" % (type(ex).__name__, ex))

    try:
        import imp
        ok = hasattr(imp, "load_source")
        add("PY003", "PY", "imp.load_source (3.4 前的配置加载梯)",
            "AVAILABLE" if ok else "MISSING",
            "" if ok else "Py3.12 起已移除, 缺失不致命(shim 终梯=exec 兜底)")
    except Exception as ex:
        add("PY003", "PY", "imp.load_source (3.4 前的配置加载梯)", "MISSING",
            "imp 模块不可用(%s) —— Py3.12 起已移除, shim 终梯=exec 兜底"
            % type(ex).__name__)

    try:
        p1 = os.path.join(out_dir(), "_probe_r.txt")
        p2 = os.path.join(out_dir(), "_probe_w.txt")
        with io.open(p1, "w") as f:
            f.write("x")
        os.replace(p1, p2)
        os.remove(p2)
        add("PY004", "PY", "os.replace (>=3.3)", "AVAILABLE")
    except Exception as ex:
        add("PY004", "PY", "os.replace (>=3.3)", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))

    try:
        os.makedirs(out_dir(), exist_ok=True)
        add("PY005", "PY", "os.makedirs(exist_ok=True) (>=3.2)", "AVAILABLE")
    except TypeError as ex:
        add("PY005", "PY", "os.makedirs(exist_ok=True) (>=3.2)", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))
    except Exception as ex:
        add("PY005", "PY", "os.makedirs(exist_ok=True) (>=3.2)", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    try:
        import ast
        ok = hasattr(ast, "AsyncFunctionDef")
        add("PY006", "PY", "ast.AsyncFunctionDef (>=3.5, 仅主脚本 --selftest 用)",
            "AVAILABLE" if ok else "MISSING",
            "" if ok else "仅影响 --selftest, NX 期刊内不执行")
    except Exception as ex:
        add("PY006", "PY", "ast.AsyncFunctionDef (>=3.5, 仅主脚本 --selftest 用)",
            "MISSING", "%s: %s" % (type(ex).__name__, ex))

    try:
        compile("def _o():\n    x = 1\n    def _i():\n        nonlocal x\n"
                "        x = 2\n        return x\n    return _i()\n",
                "<nonlocal>", "exec")
        add("PY007", "PY", "nonlocal 关键字", "AVAILABLE")
    except Exception as ex:
        add("PY007", "PY", "nonlocal 关键字", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))

    try:
        import inspect
        add("PY008", "PY", "inspect.signature (>=3.3)",
            "AVAILABLE" if hasattr(inspect, "signature") else "MISSING")
    except Exception as ex:
        add("PY008", "PY", "inspect.signature (>=3.3)", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))


# ---------------------------------------------------------------------------
# dlx 模板(逐字复用主脚本结构, 仅 NX= 属性参数化)
# ---------------------------------------------------------------------------

def _esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _group_item(gid, title, children_xml, columns=2):
    return (
        '<item Expanded="{exp}" class="UGS::UICOMP_group" hierarchy="" id="{id}" name="{id}" notes="" '
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
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_group" id="Expanded" '
        'mask="0" name="Expanded" sname="Expanded" source="2" type="logical" value="{exp}"/>'
        '<Property ClassID="UGS::UICOMP_group" group="Block Specific::" hierarchy="UGS::UICOMP_group" '
        'id="Column" mask="16384" name="Column" sname="Column" source="1" type="integer" value="{col}"/>'
        '</PropertyList></item>'
    ).format(id=gid, title=_esc(title), children=children_xml, col=columns,
             exp="True")


def _blk_enum(bid, title, labels, selected=0):
    opts = "".join('<Option name="%s" value="%d"/>' % (_esc(t), i)
                   for i, t in enumerate(labels))
    return (
        '<Property class="UICOMP_enum" hierarchy="UGS::UICOMP_group" id="{id}" mask="256" '
        'name="{id}" presentation="Enumeration" type="uicomp">'
        '<item Expanded="1" SupportsDisablingLogic="1" class="UICOMP_enum" hierarchy="" '
        'icon="styler_optionmenu.bmp" id="{id}" name="{id}" notes="" '
        'presentation="Enumeration" type="uicomp">'
        '<PropertyList id="id" mode="0">'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="API Name" mask="16656" name="API Name" sname="BlockID" source="3" type="string" '
        'value="{id}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Visibility" mask="0" name="Visibility" sname="Show" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Sensitivity" mask="0" name="Sensitivity" sname="Enable" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Group" mask="16384" name="Group" sname="Group" source="1" type="logical" '
        'value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Expanded" mask="4" name="Expanded" sname="Expanded" source="1" type="logical" '
        'value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanFocus" mask="69636" name="CanFocus" sname="CanFocus" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="CanKeyboardFocus" mask="69636" name="CanKeyboardFocus" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="ReadWrite" mask="0" name="ReadWrite" sname="RetainValue" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="UIOnly" mask="69636" name="UIOnly" sname="RetainValueInUIOnly" source="1" '
        'type="logical" value="False"/>'
        '<Property ClassID="UGS::UICOMP_widget" group="Other::" hierarchy="UGS::UICOMP_enum" '
        'id="Translated" mask="16384" name="Translated" sname="Localize" source="1" '
        'type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="TitleVisibility" mask="16384" name="TitleVisibility" sname="LabelVisibility" '
        'source="1" type="logical" value="True"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="0" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="PresentationStyle" mask="16384" '
        'name="PresentationStyle" sname="PresentationStyle" source="1" type="enum" '
        'selected="0">'
        '<Option name="Option Menu" value="0"/><Option name="Radio Box" value="1"/>'
        '<Option name="Pulldown" value="2"/></Property>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MaximumValue" mask="69636" name="MaximumValue" '
        'sname="MaximumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="MinimumValue" mask="69636" name="MinimumValue" '
        'sname="MinimumValue" source="1" type="integer" value="0"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles" mask="69636" name="Titles" sname="Items" '
        'source="1" type="utfstrings"/>'
        '<Property ClassID="UGS::UICOMP_enum" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Value" mask="69636" name="Value" '
        'sname="TEMPVALUE" source="1" type="integer" value="{sel}"/>'
        '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::UICOMP_enum" '
        'id="Title" mask="257" name="Title" sname="Label" source="1" type="utfstring" '
        'value="{title}"/>'
        '<Property ClassID="UGS::UICOMP_enum" brief="0" dynamic="1" group="Block Specific::" '
        'hierarchy="UGS::UICOMP_enum" id="Titles_1" mask="256" name="Titles_1" '
        'selected="{sel}" sname="Value" source="4" type="enum">{opts}</Property>'
        '</PropertyList></item></Property>'
    ).format(id=bid, title=_esc(title), opts=opts, sel=int(selected))


def build_probe_dlx(with_nx_attr, nx_value="2312.0.0"):
    """最小枚举对话框; with_nx_attr=False 时省略根节点 NX 属性(兼容变体B)。"""
    root = ('<Dialog ContainerItems="1" Expanded="1" class="" id="Dialog" '
            'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
            'title="NX CompatProbe" type="uicomp" version="1.0.0"')
    if with_nx_attr:
        root = ('<Dialog ContainerItems="1" Expanded="1" NX="%s" class="" id="Dialog" '
                'languageInfo="Language and Codeset: english 17" name="Dialog" notes="" '
                'title="NX CompatProbe" type="uicomp" version="1.0.0"' % nx_value)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + root + ">"
            + _group_item("grp_probe", "兼容探针",
                          _blk_enum(ENUM_BLOCK_ID, "枚举测试", ENUM_LABELS, 0),
                          columns=1)
            + '<PropertyList id="id" mode="0">'
            + '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
              'id="Title" mask="256" name="Title" sname="Label" source="1" type="utfstring" '
              'value="兼容探针"/>'
            + '<Property ClassID="UGS::UICOMP" group="General::" hierarchy="UGS::Styler::DialogItem" '
              'id="Cue" mask="256" name="Cue" sname="Cue" source="1" type="utfstring" '
              'value="NX 兼容性探针对话框"/>'
            + '</PropertyList></Dialog>\n')


# ---------------------------------------------------------------------------
# VER 组: 版本探测机制
# ---------------------------------------------------------------------------

def probe_ver(uf, session):
    if uf is None:
        add("VER001", "VER", "UF.AskVersion()", "SKIP", "无 NX 环境")
    else:
        try:
            r = uf.AskVersion()
            add("VER001", "VER", "UF.AskVersion()", "AVAILABLE", "返回: %r" % (r,))
        except Exception as ex:
            add("VER001", "VER", "UF.AskVersion()", "MISSING",
                "Python 包装不存在或调用失败: %s: %s —— 改用环境变量探测"
                % (type(ex).__name__, ex))

    v = os.environ.get("UGII_VERSION")
    add("VER002", "VER", "环境变量 UGII_VERSION",
        "INFO", v if v else "未设置(期刊进程可能不继承, 需实机确认)")

    rd = os.environ.get("UGII_ROOT_DIR")
    if rd:
        seg = ""
        for part in rd.replace("/", "\\").split("\\"):
            if part.lower().startswith("nx") or part[:1].isdigit():
                seg = part
                break
        add("VER003", "VER", "环境变量 UGII_ROOT_DIR", "INFO",
            "%s (路径段提示: %s) —— v1.1 实测可能为残留旧值, 不可单独采信"
            % (rd, seg or "无"))
    else:
        add("VER003", "VER", "环境变量 UGII_ROOT_DIR", "INFO", "未设置")

    v4 = os.environ.get("UGII_BASE_DIR") or os.environ.get("UGII_UG_DIR")
    add("VER004", "VER", "环境变量 UGII_BASE_DIR/UGII_UG_DIR",
        "INFO", v4 or "未设置")

    try:
        import NXOpen
        p = getattr(NXOpen, "__file__", "") or ""
        seg = ""
        if p:
            for part in p.replace("/", "\\").split("\\"):
                low = part.lower()
                if low.startswith("nx") or (part[:1].isdigit() and "." in part):
                    seg = part
                    break
        add("VER005", "VER", "NXOpen 模块路径版本解析(首选通道)",
            "INFO" if p else "SKIP",
            "%s (路径段提示: %s) —— NXOpen.pyd 必在运行中 NX 的安装目录下"
            % (p or "取不到 __file__", seg or "无"))
    except Exception as ex:
        add("VER005", "VER", "NXOpen 模块路径版本解析(首选通道)", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))


# ---------------------------------------------------------------------------
# API 组: NXOpen 建模 API(临时 Part 内)
# ---------------------------------------------------------------------------

def _rect_lines(nx, part, x0, y0, x1, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    cs = []
    for i in range(4):
        a = pts[i]
        b = pts[(i + 1) % 4]
        cs.append(part.Curves.CreateLine(nx.Point3d(a[0], a[1], 0.0),
                                         nx.Point3d(b[0], b[1], 0.0)))
    return cs


# --- 编组工具(版本无关): 反射拿真实签名 + 造 .NET 数组 + 载体/枚举/seed 三轴 ---
# _GOOD: S3 二分探测出的可用配方, 供 _extrude_rect 与 runner 复用。
_GOOD = {"carrier": None, "mode": None, "seed": None, "hp": None,
         "nulls": None, "arity7": True, "elem_type": None, "_notes": []}


def _reflect_overloads(obj, name):
    """反射返回该方法所有重载的(参数类型,参数名)列表; 失败返回错误标记。"""
    out = []
    try:
        t = obj.GetType()
        for m in t.GetMethods():
            try:
                if m.Name != name:
                    continue
            except Exception:
                continue
            try:
                ps = [(p.ParameterType, p.Name) for p in m.GetParameters()]
            except Exception:
                continue
            out.append(ps)
    except Exception as ex:
        return [[("REFLECT_ERR", "%s: %s" % (type(ex).__name__, ex))]]
    return out


def _fmt_overloads(ovl):
    segs = []
    for ps in ovl:
        if len(ps) == 1 and ps[0][0] == "REFLECT_ERR":
            segs.append("reflect_err(%s)" % ps[0][1])
            continue
        segs.append("(" + ", ".join("%s %s" % (pt.Name, pn) for pt, pn in ps) + ")")
    return " | ".join(segs) if segs else "无重载/未找到"


def _array_param_elem_type(obj, name, param_index):
    """反射取第 param_index 个数组参数的元素 System.Type(供 CreateInstance)。"""
    try:
        t = obj.GetType()
        for m in t.GetMethods():
            if m.Name != name:
                continue
            try:
                ps = m.GetParameters()
            except Exception:
                continue
            if len(ps) > param_index:
                pt = ps[param_index].ParameterType
                try:
                    if pt.IsArray:
                        return pt.GetElementType()
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _net_array(elem_type, items):
    """用反射拿到的元素 System.Type 造真 .NET 数组(绕开老 pythonnet Array[T] 怪癖)。"""
    import System
    a = System.Array.CreateInstance(elem_type, len(items))
    for i in range(len(items)):
        a[i] = items[i]
    return a


def _make_carriers(nx, elem_type, rule):
    """构造多种 rules 载体(仅纳入可成功构造者), 返回 [(tag, carrier)]。

    自研绑定无 .NET 数组构造通道, 故主打: list / tuple / single(不包 list) /
    coerce(把 rule 包成 SelectionIntentRule 再入 list)。NETarr* 仅在能拿到
    System/反射时纳入(NX2312 等), NX10/12 会自动跳过。"""
    carriers = [("list", [rule]), ("tuple", (rule,)), ("single", rule)]
    try:
        carriers.append(("coerce", [nx.SelectionIntentRule(rule)]))
    except Exception as ex:
        _GOOD["_notes"].append("coerce失败:%s" % ex)
    if elem_type is not None:
        try:
            carriers.append(("NETarr[reflect]", _net_array(elem_type, [rule])))
        except Exception as ex:
            _GOOD["_notes"].append("reflect_arr失败:%s" % ex)
    try:
        from System import Array
        carriers.append(("NETarr[Array[T]]", Array[nx.SelectionIntentRule]([rule])))
    except Exception as ex:
        _GOOD["_notes"].append("Array[T]失败:%s" % ex)
    try:
        carriers.append(("NETarr[.array()]", nx.SelectionIntentRule.array([rule])))
    except Exception as ex:
        _GOOD["_notes"].append(".array()失败:%s" % ex)
    return carriers


def _carrier_by_kind(nx, elem_type, rule, kind):
    """按 _GOOD 记录的载体种类, 从单个 rule 重建载体(供 _extrude_rect 复用)。"""
    if kind == "tuple":
        return (rule,)
    if kind == "single":
        return rule
    if kind == "coerce":
        try:
            return [nx.SelectionIntentRule(rule)]
        except Exception:
            return [rule]
    if kind == "NETarr[reflect]" and elem_type is not None:
        return _net_array(elem_type, [rule])
    if kind == "NETarr[Array[T]]":
        from System import Array
        return Array[nx.SelectionIntentRule]([rule])
    if kind == "NETarr[.array()]":
        return nx.SelectionIntentRule.array([rule])
    return [rule]


def _hp_by_form(nx, curves, form):
    """按记录的 helpPoint 形态重建(自研绑定可能只认某一种)。"""
    try:
        p = curves[0].StartPoint
    except Exception:
        p = nx.Point3d(0.0, 0.0, 0.0)
    if form == "NoneHP":
        return None
    try:
        xyz = (float(p.X), float(p.Y), float(p.Z))
    except Exception:
        xyz = (0.0, 0.0, 0.0)
    if form == "tuple3":
        return xyz
    if form == "list3":
        return list(xyz)
    return p


def _hp_variants(nx, curves):
    """helpPoint 候选形态(自研绑定常见隐藏卡点): Point3d / tuple3 / list3 / None。"""
    try:
        p = curves[0].StartPoint
    except Exception:
        p = nx.Point3d(0.0, 0.0, 0.0)
    try:
        xyz = (float(p.X), float(p.Y), float(p.Z))
    except Exception:
        xyz = (0.0, 0.0, 0.0)
    return [("Point3d", p), ("tuple3", xyz), ("list3", list(xyz)), ("NoneHP", None)]


def _null_variants(nx):
    """seed/connector 的 null 候选: 裸 None vs 类型化 NXObject.Null(录制日志常用后者)。"""
    nulls = [("None", None)]
    try:
        nulls.append(("NXNull", nx.NXObject.Null))
    except Exception as ex:
        _GOOD["_notes"].append("NXObject.Null不可用:%s" % ex)
    return nulls


def _null_by_form(nx, form):
    if form == "NXNull":
        try:
            return nx.NXObject.Null
        except Exception:
            return None
    return None


def _seed_by_form(nx, curves, form):
    if form == "curve":
        try:
            return curves[0]
        except Exception:
            return None
    if form == "NXNull":
        try:
            return nx.NXObject.Null
        except Exception:
            return None
    return None


def _mode_vals(nx):
    try:
        return [("enum", nx.Section.Mode.Create),
                ("int", int(nx.Section.Mode.Create))]
    except Exception:
        return [("enum", nx.Section.Mode.Create), ("int", 0)]


def _mode_by_form(nx, form):
    if form == "int":
        try:
            return int(nx.Section.Mode.Create)
        except Exception:
            return 0
    return nx.Section.Mode.Create


def _extrude_rect(nx, part, curves, name, z0=0.0, z1=10.0):
    """拉伸一组线; 复用 _extrude_chain_probe 探明的编组配方(_GOOD)。

    老版本回退通道: Feature.Null→None / CreateDirection 3参→2参;
    AddToSection 载体/枚举/seed/元数 全部按 _GOOD 记录的成功配方重建。"""
    import NXOpen.Features
    import NXOpen.GeometricUtilities
    try:
        bldr = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    except Exception:
        bldr = part.Features.CreateExtrudeBuilder(None)
    try:
        section = part.Sections.CreateSection(0.01, 0.01, 0.5)
        try:
            section.SetAllowedEntityTypes(nx.Section.AllowTypes.OnlyCurves)
        except Exception:
            pass
        bldr.Section = section
        bldr.AllowSelfIntersectingSection(True)
        rule = part.ScRuleFactory.CreateRuleBaseCurveDumb(list(curves))
        carrier = _carrier_by_kind(nx, _GOOD.get("elem_type"), rule,
                                   _GOOD.get("carrier") or "list")
        hp = _hp_by_form(nx, curves, _GOOD.get("hp") or "Point3d")
        mval = _mode_by_form(nx, _GOOD.get("mode") or "enum")
        nval = _null_by_form(nx, _GOOD.get("nulls") or "None")
        seed = _seed_by_form(nx, curves, _GOOD.get("seed") or "None")
        args = [carrier, seed, nval, nval, hp, mval]
        if _GOOD.get("arity7", True):
            args.append(False)
        try:
            section.AddToSection(*args)
        except Exception:
            section.AddToSection([rule], None, None, None,
                                 nx.Point3d(0.0, 0.0, 0.0),
                                 nx.Section.Mode.Create, False)
        bldr.Limits.StartExtend.Value.RightHandSide = str(z0)
        bldr.Limits.EndExtend.Value.RightHandSide = str(z1)
        bldr.DistanceTolerance = 0.01
        try:
            bldr.Direction = part.Directions.CreateDirection(
                nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0),
                nx.SmartObject.UpdateOption.DontUpdate)
        except TypeError:
            bldr.Direction = part.Directions.CreateDirection(
                nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0))
        try:
            bldr.BodyType = nx.Features.Feature.BodyType.Solid
        except Exception:
            pass
        bldr.BooleanOperation.Type = \
            nx.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = bldr.CommitFeature()
        try:
            feat.SetName(name)
        except Exception:
            pass
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _extrude_chain_probe(nx, part, curves, rule, section):
    """v1.1 拉伸主链逐行分步探测: 失败即停在断点。

    返回 (feat 或 None, 已通过步列表, (断点步名, 异常串) 或 None)。
    用于在 NX10 上精确定位 v1.0 的 "TypeError: 没有过载" 断行。"""
    import NXOpen.Features
    import NXOpen.GeometricUtilities
    steps = []
    bldr = None

    def _fail(tag, ex):
        return None, steps, (tag, "%s: %s" % (type(ex).__name__, ex))

    # S1 builder 创建: Feature.Null 与 None 双通道
    try:
        bldr = part.Features.CreateExtrudeBuilder(
            NXOpen.Features.Feature.Null)
        steps.append("S1 CreateExtrudeBuilder(Feature.Null)")
    except Exception:
        try:
            bldr = part.Features.CreateExtrudeBuilder(None)
            steps.append("S1 CreateExtrudeBuilder(None)[Feature.Null 不可用]")
        except Exception as ex2:
            return _fail("S1 CreateExtrudeBuilder", ex2)
    # S2 挂 section
    try:
        bldr.Section = section
        bldr.AllowSelfIntersectingSection(True)
        steps.append("S2 Section挂接/AllowSelfIntersecting")
    except Exception as ex:
        return _fail("S2 Section挂接", ex)
    # S3 AddToSection 二分。据本轮实机旁证已洗清两大嫌疑:
    #   MAR002 ReplaceRules(收 list of rule)=OK → rules 用 Python list 没问题;
    #   API002 CreateLine(收 Point3d)=OK        → helpPoint 用 Point3d 没问题。
    # 剩余卡点必在 AddToSection 独有参数: seed/两个 connector 传的裸 None(绑定
    # 可能要类型化 null NXObject.Null) 或 mode 枚举。故 Pass1 固定 carrier=list、
    # hp=Point3d, 只在 nulls × seed × mode × arity 上二分; 仍败则 Pass2 放宽载体/HP。
    elem = _array_param_elem_type(section, "AddToSection", 0)  # 仅 2312 等可拿到
    _GOOD["elem_type"] = elem
    modes = _mode_vals(nx)
    nulls = _null_variants(nx)
    arities = [(True, "7"), (False, "6")]
    try:
        hp_pt = curves[0].StartPoint
    except Exception:
        hp_pt = nx.Point3d(0.0, 0.0, 0.0)
    seed_opts = [("None", None)]
    for ntag, nval in nulls:
        if ntag != "None":
            seed_opts.append((ntag, nval))
    try:
        seed_opts.append(("curve", curves[0]))
    except Exception:
        pass
    s3_errs = []
    s3_done = None

    def _ats(carr, hval, nval, sval, mval, use7, tag):
        args = [carr, sval, nval, nval, hval, mval]
        if use7:
            args.append(False)
        try:
            section.AddToSection(*args)
            return True
        except Exception as ex:
            s3_errs.append("%s→%s" % (tag, type(ex).__name__))
            return False

    # Pass 1: carrier=list + hp=Point3d(已洗清), 只二分 nulls/seed/mode/arity
    for ntag, nval in nulls:
        for stag, sval in seed_opts:
            for mtag, mval in modes:
                for use7, atag in arities:
                    tag = "list|HP=pt|null=%s|seed=%s|mode=%s|%s参" % (
                        ntag, stag, mtag, atag)
                    if _ats([rule], hp_pt, nval, sval, mval, use7, tag):
                        s3_done = ("list", "Point3d", mtag, stag, ntag, use7)
                        break
                if s3_done:
                    break
            if s3_done:
                break
        if s3_done:
            break
    # Pass 2: 放宽 rules 载体 与 helpPoint 形态
    if s3_done is None:
        for ctag, carr in _make_carriers(nx, elem, rule):
            for htag, hval in _hp_variants(nx, curves):
                for ntag, nval in nulls:
                    for stag, sval in seed_opts:
                        for mtag, mval in modes:
                            for use7, atag in arities:
                                tag = "%s|HP=%s|null=%s|seed=%s|mode=%s|%s参" % (
                                    ctag, htag, ntag, stag, mtag, atag)
                                if _ats(carr, hval, nval, sval, mval, use7, tag):
                                    s3_done = (ctag, htag, mtag, stag, ntag, use7)
                                    break
                            if s3_done:
                                break
                        if s3_done:
                            break
                    if s3_done:
                        break
                if s3_done:
                    break
            if s3_done:
                break
    if s3_done:
        _GOOD["carrier"], _GOOD["hp"], _GOOD["mode"] = \
            s3_done[0], s3_done[1], s3_done[2]
        _GOOD["seed"], _GOOD["nulls"], _GOOD["arity7"] = \
            s3_done[3], s3_done[4], s3_done[5]
        steps.append("S3 AddToSection[载体=%s HP=%s null=%s seed=%s 枚举=%s %s参]"
                     % (s3_done[0], s3_done[1], s3_done[4], s3_done[3],
                        s3_done[2], "7" if s3_done[5] else "6"))
    else:
        return _fail("S3 AddToSection",
                     "两遍二分(含类型化null轴)全败, 真实签名见 API021 __doc__: %s"
                     % " ‖ ".join(s3_errs[:24]))
    # S4 Limits
    try:
        bldr.Limits.StartExtend.Value.RightHandSide = "0.0"
        bldr.Limits.EndExtend.Value.RightHandSide = "10.0"
        bldr.DistanceTolerance = 0.01
        steps.append("S4 Limits/DistanceTolerance")
    except Exception as ex:
        return _fail("S4 Limits", ex)
    # S5 Direction: 3参 → 2参
    try:
        try:
            bldr.Direction = part.Directions.CreateDirection(
                nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0),
                nx.SmartObject.UpdateOption.DontUpdate)
        except TypeError:
            bldr.Direction = part.Directions.CreateDirection(
                nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0))
        steps.append("S5 CreateDirection")
    except Exception as ex:
        return _fail("S5 CreateDirection", ex)
    # S6 BodyType + BooleanType
    try:
        try:
            bldr.BodyType = nx.Features.Feature.BodyType.Solid
        except Exception:
            pass
        bldr.BooleanOperation.Type = \
            nx.GeometricUtilities.BooleanOperation.BooleanType.Create
        steps.append("S6 BodyType/BooleanType")
    except Exception as ex:
        return _fail("S6 BodyType/BooleanType", ex)
    # S7 Commit
    try:
        feat = bldr.CommitFeature()
        steps.append("S7 CommitFeature")
    except Exception as ex:
        try:
            bldr.Destroy()
        except Exception:
            pass
        return _fail("S7 CommitFeature", ex)
    try:
        bldr.Destroy()
    except Exception:
        pass
    return feat, steps, None


def _addtosection_introspect(nx, section, rule):
    """API019: S3 失败时反射报出 AddToSection 真实托管签名 + 各载体构造情况。"""
    bits = []
    try:
        bits.append("反射重载=%s" % _fmt_overloads(
            _reflect_overloads(section, "AddToSection")))
    except Exception as ex:
        bits.append("反射失败:%s" % ex)
    try:
        elem = _GOOD.get("elem_type")
        bits.append("rules元素类型=%s"
                    % (getattr(elem, "FullName", None) or "反射未取到"))
    except Exception as ex:
        bits.append("元素类型自省失败:%s" % ex)
    for n in _GOOD.get("_notes", []):
        bits.append(n)
    try:
        mode = nx.Section.Mode.Create
        bits.append("Mode类型=%s int?=%s"
                    % (type(mode).__name__, getattr(mode, "__int__", None)))
    except Exception as ex:
        bits.append("Mode自省失败:%s" % ex)
    try:
        bits.append("rule类型=%s" % type(rule).__name__)
    except Exception as ex:
        bits.append("rule类型自省失败:%s" % ex)
    add("API019", "API", "Section.AddToSection 反射自省", "INFO", " ; ".join(bits))


def _dump_method_sig(rid, label, obj, name):
    """抓自研绑定方法的 __doc__/overloads/inspect.signature → 无反射时的权威签名源。"""
    bits = []
    try:
        m = getattr(obj, name)
        bits.append("type=%s" % type(m).__name__)
    except Exception as ex:
        add(rid, "API", label, "ERROR", "getattr失败:%s: %s"
            % (type(ex).__name__, ex))
        return
    try:
        doc = getattr(m, "__doc__", None)
        d = doc if doc else ""
        bits.append("__doc__=%s" % (d[:1600] if d else "None"))
    except Exception as ex:
        bits.append("__doc__取不到:%s" % ex)
    for attr in ("overloads", "__overloads__", "Overloads", "__ signatures__"):
        try:
            ov = getattr(m, attr)
            if ov is not None:
                bits.append("%s=%r" % (attr, ov))
        except Exception:
            pass
    try:
        import inspect
        bits.append("sig=%s" % (inspect.signature(m),))
    except Exception as ex:
        bits.append("sig=%s" % type(ex).__name__)
    add(rid, "API", label, "INFO", " ; ".join(bits))


def probe_binding_signatures(nx, section, part):
    """API021~024: 抓绑定自带签名文本。NX10/12 无 pythonnet/反射, __doc__ 是唯一
    能看到 AddToSection 真实可接受类型的通道; 对照 dump 一个收 list 成功的方法
    (CreateRuleBaseCurveDumb) 与主脚本同样传 list 的方法, 直接揭示数组参数约定。"""
    _dump_method_sig("API021", "Section.AddToSection 签名(卡点)",
                     section, "AddToSection")
    _dump_method_sig("API022", "ScRuleFactory.CreateRuleBaseCurveDumb 签名(对照:list可用)",
                     part.ScRuleFactory, "CreateRuleBaseCurveDumb")
    _dump_method_sig("API023", "ScRuleFactory.CreateRuleFaceDumb 签名(主脚本传list)",
                     part.ScRuleFactory, "CreateRuleFaceDumb")
    _dump_method_sig("API024", "Features.CreateUniteFeature 签名(主脚本传list)",
                     part.Features, "CreateUniteFeature")
    _dump_method_sig("API025", "ScRuleFactory.CreateRuleOuterEdgesOfFaces 签名(圆角用)",
                     part.ScRuleFactory, "CreateRuleOuterEdgesOfFaces")


# ---------------------------------------------------------------------------
# MAR 组: runner 其余数组参数调用点的 list-vs-.NET数组 编组体检
# ---------------------------------------------------------------------------

def _mar_report(rid, label, list_ok, arr_ok, note=""):
    if list_ok:
        verdict = "list可用(runner 无需改)"
    elif arr_ok:
        verdict = "需.NET数组(runner _na() 覆盖)"
    else:
        verdict = "两者皆败(需查真实签名)"
    add(rid, "MAR", label, "INFO",
        "list=%s; NETarr=%s; 判定=%s%s"
        % ("OK" if list_ok else "FAIL", "OK" if arr_ok else "FAIL", verdict,
           ("; " + note) if note else ""))


def _mk_arr(receiver, method, pidx, items):
    et = _array_param_elem_type(receiver, method, pidx)
    if et is None:
        return None
    try:
        return _net_array(et, items)
    except Exception:
        return None


def probe_marshalling(nx, session, part, body1, united_body, tool_body):
    """逐个数组参数调用点测 '传 Python list' vs '传 .NET 数组' 谁可用,
    精确框定 runner 里 _na() 覆盖面。全在临时 Part 内, 不保存; 属性/建对象类
    调用可安全重复, 故不污染判定。注: NX10/12 无 System, .NET 数组构造会失败,
    此时 NETarr=FAIL 不代表方法不可用, 只代表 list 是否够用 —— 看 list 列即可。"""
    import NXOpen.Features

    # MAR001 BooleanOperation.SetTargetBodies
    try:
        b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        bo = b.BooleanOperation
        tgt = body1
        lo = ao = False
        if tgt is not None:
            try:
                bo.SetTargetBodies([tgt]); lo = True
            except Exception:
                pass
            a = _mk_arr(bo, "SetTargetBodies", 0, [tgt])
            if a is not None:
                try:
                    bo.SetTargetBodies(a); ao = True
                except Exception:
                    pass
        try:
            b.Destroy()
        except Exception:
            pass
        _mar_report("MAR001", "BooleanOperation.SetTargetBodies", lo, ao,
                    "无目标体" if tgt is None else "")
    except Exception as ex:
        add("MAR001", "MAR", "BooleanOperation.SetTargetBodies", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # MAR002 ScCollector.ReplaceRules
    try:
        rule = part.ScRuleFactory.CreateRuleBaseCurveDumb(
            list(_rect_lines(nx, part, 80.0, 0.0, 90.0, 10.0)))
        sc = part.ScCollectors.CreateCollector()
        lo = ao = False
        try:
            sc.ReplaceRules([rule], False); lo = True
        except Exception:
            pass
        a = _mk_arr(sc, "ReplaceRules", 0, [rule])
        if a is not None:
            try:
                sc.ReplaceRules(a, False); ao = True
            except Exception:
                pass
        _mar_report("MAR002", "ScCollector.ReplaceRules", lo, ao)
    except Exception as ex:
        add("MAR002", "MAR", "ScCollector.ReplaceRules", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # MAR003 MeasureManager.NewMassProperties (两个数组参数: 单位 + 体)
    try:
        mm = part.MeasureManager
        unit = part.UnitCollection.FindObject("MilliMeter")
        tgt = united_body or body1
        lo = ao = False
        if tgt is not None and unit is not None:
            try:
                mm.NewMassProperties([unit] * 5, 0.99, [tgt]); lo = True
            except Exception:
                pass
            au = _mk_arr(mm, "NewMassProperties", 0, [unit] * 5)
            ab = _mk_arr(mm, "NewMassProperties", 2, [tgt])
            if au is not None and ab is not None:
                try:
                    mm.NewMassProperties(au, 0.99, ab); ao = True
                except Exception:
                    pass
        _mar_report("MAR003", "MeasureManager.NewMassProperties(单位+体)",
                    lo, ao, "缺体/单位" if (tgt is None or unit is None) else "")
    except Exception as ex:
        add("MAR003", "MAR", "MeasureManager.NewMassProperties(单位+体)", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # MAR004 DisplayModification.Apply (DisplayManager 在 session 上, 非 part)
    try:
        dm = session.DisplayManager.NewDisplayModification()
        tgt = [body1] if body1 is not None else []
        lo = ao = False
        if tgt:
            try:
                dm.Apply(tgt); lo = True
            except Exception:
                pass
            a = _mk_arr(dm, "Apply", 0, tgt)
            if a is not None:
                try:
                    dm.Apply(a); ao = True
                except Exception:
                    pass
        try:
            dm.Dispose()
        except Exception:
            pass
        _mar_report("MAR004", "DisplayModification.Apply", lo, ao,
                    "无体可测" if not tgt else "")
    except Exception as ex:
        add("MAR004", "MAR", "DisplayModification.Apply", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # MAR005/006 布尔特征真实签名(仅反射, 不建特征以免污染几何)
    for mid, mname in (("MAR005", "CreateUniteFeature"),
                       ("MAR006", "CreateSubtractFeature")):
        try:
            add(mid, "MAR", "Features.%s 反射签名" % mname, "INFO",
                _fmt_overloads(_reflect_overloads(part.Features, mname)))
        except Exception as ex:
            add(mid, "MAR", "Features.%s 反射签名" % mname, "ERROR",
                "%s: %s" % (type(ex).__name__, ex))


def _flat_face(uf, body):
    """取第一个平面(d[4]=球半径近似0 的面, 与主脚本 _find_flat_face 同判据)。"""
    try:
        faces = list(body.GetFaces())
    except Exception:
        return None, []
    flat = None
    for f in faces:
        if uf is not None:
            try:
                d = uf.Modeling.AskFaceData(f.Tag)
                if float(d[4]) < 1e-9:
                    flat = f
                    break
            except Exception:
                pass
    return (flat or (faces[0] if faces else None)), faces


def _close_part(nx, part):
    """临时 Part 尽力关闭(关闭失败无害, 记录原因)。"""
    cw = nx.BasePart.CloseWholeTree
    cm = nx.BasePart.CloseModified
    for wname, mname in (("FalseValue", "CloseModified"),
                         ("False", "CloseModified"),
                         ("False_", "UseResponses")):
        try:
            w = getattr(cw, wname)
            m = getattr(cm, mname)
            part.Close(w, m, None)
            return "已关闭(%s/%s)" % (wname, mname)
        except Exception:
            continue
    return "未关闭(无害, 退出 NX 时自动释放)"


def probe_api(nx, session, uf):
    # --- API001 临时 Part ---------------------------------------------------
    part = None
    try:
        session.Parts.NewDisplay(TEMP_PART_NAME, nx.Part.Units.Millimeters)
        part = session.Parts.Work
    except Exception as ex:
        add("API001", "API", "新建临时 Part (NewDisplay+Work)", "ERROR",
            "%s: %s —— API 组全部跳过" % (type(ex).__name__, ex))
    if part is None:
        for i in range(2, 26):
            add("API%03d" % i, "API", "(前置失败)", "SKIP", "API001 失败")
        for i in range(1, 7):
            add("MAR%03d" % i, "MAR", "(前置失败)", "SKIP", "API001 失败")
        return
    add("API001", "API", "新建临时 Part (NewDisplay+Work)", "AVAILABLE")

    # --- API002 CreateLine --------------------------------------------------
    try:
        ln = part.Curves.CreateLine(nx.Point3d(0.0, 0.0, 0.0),
                                    nx.Point3d(10.0, 0.0, 0.0))
        add("API002", "API", "Curves.CreateLine", "AVAILABLE", "tag=%s" % ln.Tag)
    except Exception as ex:
        ln = None
        add("API002", "API", "Curves.CreateLine", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # --- API003 CreateArc 双签名(矩阵/向量) ----------------------------------
    # v1.1: 三候选集合名逐一报告(NX10 实测 Matrices/PointMatrices 均不存在,
    # 老版应为 NXMatrices)
    mtx = None
    mtx_name = ""
    mtx_seen = []
    for _attr in ("NXMatrices", "Matrices", "PointMatrices"):
        coll = getattr(part, _attr, None)
        if coll is not None:
            mtx_seen.append(_attr)
            if hasattr(coll, "CreateMatrix"):
                try:
                    mtx = coll.CreateMatrix(nx.NXMatrix3d(
                        1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
                    mtx_name = _attr
                    break
                except Exception:
                    mtx = None
    arc_m = arc_v = None
    err_m = err_v = ""
    c = nx.Point3d(20.0, 0.0, 0.0)
    if mtx is not None:
        try:
            arc_m = part.Curves.CreateArc(c, mtx, 5.0, 0.0, 2.0)
        except Exception as ex:
            err_m = "%s: %s" % (type(ex).__name__, ex)
    else:
        err_m = "矩阵集合不可用(存在的集合: %s)" % (
            ", ".join(mtx_seen) if mtx_seen else
            "NXMatrices/Matrices/PointMatrices 均无")
    try:
        arc_v = part.Curves.CreateArc(c, nx.Vector3d(1.0, 0.0, 0.0),
                                      nx.Vector3d(0.0, 1.0, 0.0),
                                      5.0, 0.0, 2.0)
    except Exception as ex:
        err_v = "%s: %s" % (type(ex).__name__, ex)
    if arc_m is not None or arc_v is not None:
        add("API003", "API", "Curves.CreateArc 双签名",
            "AVAILABLE",
            "矩阵集合=%s; 矩阵版=%s; 向量版=%s (向量版可用即满足主脚本回退)"
            % (mtx_name or "无",
               "OK" if arc_m is not None else ("失败: " + err_m),
               "OK" if arc_v is not None else ("失败: " + err_v)))
    else:
        add("API003", "API", "Curves.CreateArc 双签名", "MISSING",
            "矩阵版: %s | 向量版: %s" % (err_m, err_v))

    # --- API004~006 拉伸主链(v1.1 分步探测, 精确定位断行) ---------------------
    body1 = None
    cs = None
    try:
        cs = _rect_lines(nx, part, 0.0, 0.0, 40.0, 30.0)
    except Exception as ex:
        cs = None
        add("API004", "API", "ScRuleFactory.CreateRuleBaseCurveDumb", "ERROR",
            "前置矩形线创建失败: %s: %s" % (type(ex).__name__, ex))

    rule = None
    if cs is not None:
        try:
            rule = part.ScRuleFactory.CreateRuleBaseCurveDumb(list(cs))
            add("API004", "API", "ScRuleFactory.CreateRuleBaseCurveDumb",
                "AVAILABLE", "NX8.5.0 起官方存在, 实测确认(接受 Python list)")
        except Exception as ex:
            add("API004", "API", "ScRuleFactory.CreateRuleBaseCurveDumb",
                "ERROR", "%s: %s" % (type(ex).__name__, ex))

    section = None
    if rule is not None:
        try:
            section = part.Sections.CreateSection(0.01, 0.01, 0.5)
            try:
                section.SetAllowedEntityTypes(nx.Section.AllowTypes.OnlyCurves)
                sub = "含 SetAllowedEntityTypes(OnlyCurves)"
            except Exception:
                sub = "CreateSection OK; SetAllowedEntityTypes 不可用(主脚本可降级)"
            add("API005", "API", "Sections.CreateSection(+OnlyCurves)",
                "AVAILABLE", sub)
        except Exception as ex:
            add("API005", "API", "Sections.CreateSection(+OnlyCurves)", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API005", "API", "Sections.CreateSection(+OnlyCurves)", "SKIP",
            "前置失败")

    if section is not None:
        try:
            probe_binding_signatures(nx, section, part)
        except Exception as ex:
            add("API021", "API", "绑定签名自省未捕获异常", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
        feat1, steps, fail_at = _extrude_chain_probe(nx, part, cs, rule,
                                                     section)
        if feat1 is not None:
            try:
                body1 = feat1.GetBodies()[0]
            except Exception:
                body1 = None
            add("API006", "API", "ExtrudeBuilder 全链 CommitFeature",
                "AVAILABLE", "全部步通过: " + " > ".join(steps))
            _carr = {"single": "rule", "coerce": "[SelectionIntentRule(rule)]",
                     "tuple": "(rule,)"}.get(_GOOD.get("carrier"), "[rule]")
            _seed = {"curve": "curve", "NXNull": "NXOpen.NXObject.Null"}.get(
                _GOOD.get("seed"), "None")
            _conn = "NXOpen.NXObject.Null" if _GOOD.get("nulls") == "NXNull" else "None"
            _hp = {"tuple3": "(x,y,z)", "list3": "[x,y,z]",
                   "NoneHP": "None"}.get(_GOOD.get("hp"), "Point3d")
            _mode = "0" if _GOOD.get("mode") == "int" else "NXOpen.Section.Mode.Create"
            add("API020", "API", "AddToSection 可用配方(runner 照此写)", "INFO",
                "载体=%s; HP=%s; null=%s; seed=%s; 枚举=%s; %s参 ‖ 示例: "
                "section.AddToSection(%s, %s, %s, %s, %s, %s%s)"
                % (_GOOD.get("carrier"), _GOOD.get("hp"), _GOOD.get("nulls"),
                   _GOOD.get("seed"), _GOOD.get("mode"),
                   "7" if _GOOD.get("arity7") else "6",
                   _carr, _seed, _conn, _conn, _hp, _mode,
                   ", False" if _GOOD.get("arity7") else ""))
        else:
            add("API006", "API", "ExtrudeBuilder 全链 CommitFeature", "ERROR",
                "断在步骤 [%s]: %s ‖ 已通过: %s —— 即该版本拉伸主链真实断点"
                % (fail_at[0], fail_at[1], " > ".join(steps)))
            _addtosection_introspect(nx, section, rule)
    else:
        add("API006", "API", "ExtrudeBuilder 全链 CommitFeature", "SKIP",
            "前置失败")

    # --- API007 Unite / API008 Subtract(保件) -------------------------------
    united_body = None
    tool_body = None
    if body1 is not None:
        try:
            cs2 = _rect_lines(nx, part, 30.0, 0.0, 70.0, 30.0)
            feat2 = _extrude_rect(nx, part, cs2, "CAD3D_PROBE_TOOL1")
            b2 = feat2.GetBodies()[0]
            fn = "CreateUniteFeature"
            r = None
            try:
                r = getattr(part.Features, fn)(body1, False, [b2], False, False)
            except TypeError:
                r = getattr(part.Features, fn)(body1, False, [b2], False,
                                               False, False, False)
            if isinstance(r, tuple):
                r = r[0]
            feats_u = list(r)
            united_body = feats_u[0].GetBodies()[0]
            add("API007", "API", "CreateUniteFeature (5参/7参)", "AVAILABLE",
                "成功签名=%s参" % ("5" if feats_u else "?"))
        except TypeError as ex:
            add("API007", "API", "CreateUniteFeature (5参/7参)", "MISSING",
                "两种签名均 TypeError: %s" % ex)
        except Exception as ex:
            add("API007", "API", "CreateUniteFeature (5参/7参)", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
        try:
            cs3 = _rect_lines(nx, part, 10.0, 10.0, 30.0, 20.0)
            feat3 = _extrude_rect(nx, part, cs3, "CAD3D_PROBE_TOOL2")
            b3 = feat3.GetBodies()[0]
            r = None
            try:
                r = part.Features.CreateSubtractFeature(
                    united_body or body1, False, [b3], True, False)
            except TypeError:
                r = part.Features.CreateSubtractFeature(
                    united_body or body1, False, [b3], True, False, False, False)
            if isinstance(r, tuple):
                r = r[0]
            feats_s = list(r)
            tool_body = b3
            add("API008", "API", "CreateSubtractFeature(保件 retain_tools=True)",
                "AVAILABLE", "工具体保留用于 API011 删面测试")
        except Exception as ex:
            add("API008", "API", "CreateSubtractFeature(保件 retain_tools=True)",
                "ERROR", "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API007", "API", "CreateUniteFeature (5参/7参)", "SKIP", "前置失败")
        add("API008", "API", "CreateSubtractFeature(保件 retain_tools=True)",
            "SKIP", "前置失败")

    # --- API009 Promotion ----------------------------------------------------
    try:
        import NXOpen.Features
        pb = part.Features.CreatePromotionBuilder(NXOpen.Features.Promotion.Null)
        note = []
        try:
            pb.Associative = False
            note.append("Associative OK")
        except Exception as ex:
            note.append("Associative 失败: %s" % ex)
        target = tool_body or united_body or body1
        if target is not None:
            try:
                pb.Body.Add(target)
                note.append("Body.Add OK")
                try:
                    pb.CommitFeature()
                    note.append("CommitFeature OK")
                except Exception as ex:
                    note.append("CommitFeature 失败(非装配上下文可接受): %s" % ex)
            except Exception as ex:
                note.append("Body.Add 失败: %s" % ex)
        try:
            pb.Destroy()
        except Exception:
            pass
        add("API009", "API", "CreatePromotionBuilder", "AVAILABLE",
            "; ".join(note))
    except Exception as ex:
        add("API009", "API", "CreatePromotionBuilder", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))

    # --- API010 EdgeBlend 全属性 --------------------------------------------
    blend_target = tool_body or united_body or body1
    if blend_target is not None:
        try:
            import NXOpen.Features
            bldr = part.Features.CreateEdgeBlendBuilder(
                NXOpen.Features.Feature.Null)
            face, _faces = _flat_face(uf, blend_target)
            sc = part.ScCollectors.CreateCollector()
            opts = None
            try:
                opts = part.ScRuleFactory.CreateRuleOptions()
                try:
                    opts.SetSelectedFromInactive(False)
                except Exception:
                    pass
            except Exception:
                opts = None
            rule = None
            try:
                if opts is not None:
                    rule = part.ScRuleFactory.CreateRuleOuterEdgesOfFaces(
                        [face], opts)
                else:
                    rule = part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
            except TypeError:
                try:
                    rule = part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
                except Exception as ex:
                    rule = None
                    add("API010", "API", "EdgeBlendBuilder 链", "MISSING",
                        "CreateRuleOuterEdgesOfFaces 两种签名均失败: %s" % ex)
            if rule is not None:
                sc.ReplaceRules([rule], False)
                filt = "OK"
                try:
                    sc.AddEvaluationFilter(nx.ScEvaluationFiltertype.LaminarEdge)
                except Exception as ex:
                    filt = "不可用: %s" % ex
                # 核心属性(主脚本 L2894-2898, 无守卫区)
                prop_detail = []
                core = [("Tolerance", 0.01), ("AllInstancesOption", False),
                        ("RemoveSelfIntersection", True),
                        ("PatchComplexGeometryAreas", True),
                        ("LimitFailingAreas", True)]
                behavior = [("ConvexConcaveY", False),
                            ("RollOverSmoothEdge", True),
                            ("RollOntoEdge", True), ("MoveSharpEdge", True),
                            ("TrimmingOption", False)]
                enums = [("OverlapOption", "Overlap.AnyConvexityRollOver"),
                         ("BlendOrder", "OrderOfBlending.ConvexFirst"),
                         ("SetbackOption", "Setback.SeparateFromCorner"),
                         ("BlendFaceContinuity", "FaceContinuity.Tangent")]
                miss_core = []
                miss_beh = []
                miss_enum = []
                for pname, val in core + behavior:
                    try:
                        setattr(bldr, pname, val)
                        prop_detail.append("%s=OK" % pname)
                    except Exception as ex:
                        prop_detail.append("%s=缺失(%s)" % (pname, ex))
                        if pname in dict(core):
                            miss_core.append(pname)
                        else:
                            miss_beh.append(pname)
                for pname, path in enums:
                    try:
                        cls, member = path.split(".")
                        val = getattr(getattr(NXOpen.Features.EdgeBlendBuilder,
                                              cls), member)
                        setattr(bldr, pname, val)
                        prop_detail.append("%s=%s OK" % (pname, path))
                    except Exception as ex:
                        prop_detail.append("%s=%s 缺失(%s)" % (pname, path, ex))
                        miss_enum.append(pname)
                chain = "OK"
                try:
                    bldr.AddChainset(sc, "3.9")
                except Exception as ex:
                    chain = "失败: %s" % ex
                commit = "未试(链集失败)"
                if chain == "OK":
                    try:
                        bldr.CommitFeature()
                        commit = "OK"
                    except Exception as ex:
                        commit = "失败: %s" % ex
                try:
                    bldr.Destroy()
                except Exception:
                    pass
                ok_core = (chain == "OK")
                add("API010", "API", "EdgeBlendBuilder 全属性+AddChainset",
                    "AVAILABLE" if ok_core else "MISSING",
                    "opts=%s; LaminarEdge=%s; %s; AddChainset=%s; Commit=%s%s"
                    % ("有" if opts is not None else "无(旧版走单参rule)",
                       filt, "; ".join(prop_detail), chain, commit,
                       ("; ⚠核心属性缺失:%s" % ",".join(miss_core)) if miss_core else ""))
            if opts is not None:
                try:
                    opts.Dispose()
                except Exception:
                    pass
        except Exception as ex:
            add("API010", "API", "EdgeBlendBuilder 全属性+AddChainset", "MISSING",
                "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API010", "API", "EdgeBlendBuilder 全属性+AddChainset", "SKIP",
            "前置失败")

    # --- API011 DeleteFace ----------------------------------------------------
    df_target = tool_body or blend_target
    if df_target is not None:
        try:
            import NXOpen.Features
            face, _f = _flat_face(uf, df_target)
            bldr = part.Features.CreateDeleteFaceBuilder(
                NXOpen.Features.Feature.Null)
            note = []
            try:
                bldr.Type = NXOpen.Features.DeleteFaceBuilder.SelectTypes.Face
                note.append("SelectTypes.Face OK")
            except Exception as ex:
                note.append("SelectTypes.Face 失败: %s" % ex)
            opts = None
            try:
                opts = part.ScRuleFactory.CreateRuleOptions()
            except Exception:
                opts = None
            try:
                if opts is not None:
                    rule = part.ScRuleFactory.CreateRuleFaceDumb([face], opts)
                else:
                    rule = part.ScRuleFactory.CreateRuleFaceDumb([face])
            except TypeError:
                rule = part.ScRuleFactory.CreateRuleFaceDumb([face])
            bldr.FaceCollector.ReplaceRules([rule], False)
            note.append("FaceCollector.ReplaceRules OK(opts=%s)"
                        % ("有" if opts is not None else "无/旧版单参"))
            try:
                bldr.Commit()
                note.append("Commit OK")
            except Exception as ex:
                note.append("Commit 失败(几何原因可接受): %s" % ex)
            try:
                bldr.Destroy()
            except Exception:
                pass
            add("API011", "API", "CreateDeleteFaceBuilder 链", "AVAILABLE",
               "; ".join(note))
        except Exception as ex:
            add("API011", "API", "CreateDeleteFaceBuilder 链", "MISSING",
                "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API011", "API", "CreateDeleteFaceBuilder 链", "SKIP", "前置失败")

    # --- API012 RemoveParameters ---------------------------------------------
    try:
        bld = part.Features.CreateRemoveParametersBuilder()
        n = 0
        for b in [b for b in [tool_body, united_body, body1] if b is not None]:
            try:
                bld.Objects.Add(b)
                n += 1
            except Exception:
                pass
        bld.Commit()
        try:
            bld.Destroy()
        except Exception:
            pass
        add("API012", "API", "CreateRemoveParametersBuilder", "AVAILABLE",
            "加入 %d 体, Commit OK" % n)
    except Exception as ex:
        add("API012", "API", "CreateRemoveParametersBuilder", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))

    # --- API013 MeasureManager ------------------------------------------------
    body_m = united_body or body1
    if body_m is not None:
        try:
            mm = part.MeasureManager
            unit_mm = part.UnitCollection.FindObject("MilliMeter")
            got_n = None
            mp = None
            err_last = ""
            for n in (5, 1, 2, 3, 4, 6, 7, 8):
                try:
                    mp = mm.NewMassProperties([unit_mm] * n, 0.99, [body_m])
                    got_n = n
                    break
                except Exception as ex:
                    err_last = "%s: %s" % (type(ex).__name__, ex)
            if mp is None:
                add("API013", "API", "MeasureManager.NewMassProperties",
                    "MISSING", "单位个数 1~8 均失败, 最后: %s" % err_last)
            else:
                vol = None
                way = ""
                try:
                    vol = float(mp.Volume())
                    way = "Volume()方法"
                except Exception:
                    try:
                        vol = float(mp.Volume)
                        way = "Volume属性"
                    except Exception as ex:
                        way = "取体积失败: %s" % ex
                add("API013", "API", "MeasureManager.NewMassProperties",
                    "AVAILABLE", "单位个数=%d; %s; vol=%.3f"
                    % (got_n, way, vol if vol is not None else -1.0))
        except Exception as ex:
            add("API013", "API", "MeasureManager.NewMassProperties", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API013", "API", "MeasureManager.NewMassProperties", "SKIP",
            "前置失败")

    # --- API014 UF.Modeling.AskFaceData ---------------------------------------
    if uf is None:
        add("API014", "API", "UF.Modeling.AskFaceData", "SKIP", "无 UF 会话")
    elif body_m is not None:
        try:
            f0 = list(body_m.GetFaces())[0]
            d = uf.Modeling.AskFaceData(f0.Tag)
            add("API014", "API", "UF.Modeling.AskFaceData", "AVAILABLE",
                "7元组 type=%s point=%r" % (d[0], d[1]))
        except Exception as ex:
            add("API014", "API", "UF.Modeling.AskFaceData", "MISSING",
                "%s: %s" % (type(ex).__name__, ex))
    else:
        add("API014", "API", "UF.Modeling.AskFaceData", "SKIP", "前置失败")

    # --- API015 DisplayManager ------------------------------------------------
    try:
        dm = session.DisplayManager.NewDisplayModification()
        dm.ApplyToAllFaces = True
        dm.ApplyToOwningParts = False
        dm.NewColor = 186
        dm.NewTranslucency = 78
        applied = ""
        if body_m is not None:
            try:
                dm.Apply([body_m])
                applied = "Apply OK"
            except Exception as ex:
                applied = "Apply 失败(可接受): %s" % ex
        dm.Dispose()
        add("API015", "API", "DisplayManager.NewDisplayModification",
            "AVAILABLE", applied or "创建/Dispose OK")
    except Exception as ex:
        add("API015", "API", "DisplayManager.NewDisplayModification", "MISSING",
            "%s: %s" % (type(ex).__name__, ex))

    # --- API016 LayerCategories ------------------------------------------------
    try:
        cats = getattr(part, "LayerCategories", None)
        if cats is None:
            add("API016", "API", "LayerCategories", "MISSING",
                "part 无 LayerCategories 属性(主脚本 getattr 已降级)")
        else:
            try:
                cats.CreateCategory("PROBE_CAT", "probe (CAD3D)", [11])
                add("API016", "API", "LayerCategories", "AVAILABLE",
                    "CreateCategory(name, desc, [11]) OK")
            except Exception as ex:
                add("API016", "API", "LayerCategories", "ERROR",
                    "存在但 CreateCategory 失败: %s: %s"
                    % (type(ex).__name__, ex))
    except Exception as ex:
        add("API016", "API", "LayerCategories", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # --- API017 AddComponent 双签名 --------------------------------------------
    std_dir = os.path.join(script_dir(), "stdparts")
    prt = None
    if os.path.isdir(std_dir):
        cands = sorted(f for f in os.listdir(std_dir)
                       if f.lower().endswith(".prt"))
        if cands:
            prt = os.path.join(std_dir, cands[0])
    if prt is None:
        add("API017", "API", "ComponentAssembly.AddComponent 双签名", "SKIP",
            "未找到 stdparts\\*.prt 测试件(将探针与 stdparts 目录一同放置可测此项)")
    else:
        try:
            ca = part.ComponentAssembly
            m3 = nx.Matrix3x3()
            m3.Xx, m3.Xy, m3.Xz = 1.0, 0.0, 0.0
            m3.Yx, m3.Yy, m3.Yz = 0.0, 1.0, 0.0
            m3.Zx, m3.Zy, m3.Zz = 0.0, 0.0, 1.0
            try:
                comp, _ls = ca.AddComponent(prt, "MODEL", "PROBE",
                                            nx.Point3d(200.0, 200.0, 0.0),
                                            m3, -1)
                sig = "6参"
            except TypeError:
                comp = ca.AddComponent(prt, "MODEL", "PROBE",
                                       nx.Point3d(200.0, 200.0, 0.0),
                                       m3, -1, False)
                sig = "7参"
            try:      # 删除探针组件, 不留痕迹
                for ch in list(ca.RootComponent.GetChildren()):
                    if ch.Name in ("PROBE",):
                        part.ComponentAssembly.RemoveComponent(ch)
            except Exception:
                pass
            add("API017", "API", "ComponentAssembly.AddComponent 双签名",
                "AVAILABLE", "成功签名=%s; 件=%s"
                % (sig, os.path.basename(prt)))
        except Exception as ex:
            hint = ""
            msg = "%s" % ex
            if ("更新版本" in msg or "不是部件文件" in msg or
                    "newer version" in msg.lower()):
                hint = (" —— 判读: %s 为较新 NX 格式, 老版本无法加载。"
                        "交付侧动作: 在 NX2312 中 文件→选项→保存选项→"
                        "部件文件版本 设为兼容目标旧版后重新另存 stdparts 全部件"
                        % os.path.basename(prt))
            add("API017", "API", "ComponentAssembly.AddComponent 双签名",
                "ERROR", "%s: %s%s" % (type(ex).__name__, ex, hint))

    # --- MAR 组: 各数组参数编组体检(定位 runner _na() 覆盖面) --------------------
    try:
        probe_marshalling(nx, session, part, body1, united_body, tool_body)
    except Exception as ex:
        add("MAR999", "MAR", "编组体检未捕获异常", "ERROR",
            "%s: %s" % (type(ex).__name__, ex))

    # --- 收尾: 关闭临时 Part -----------------------------------------------------
    try:
        note = _close_part(nx, part)
        add("API018", "API", "临时 Part 清理", "INFO", note)
    except Exception as ex:
        add("API018", "API", "临时 Part 清理", "INFO",
            "关闭异常(无害): %s" % ex)


# ---------------------------------------------------------------------------
# UI 组: BlockStyler 对话框
# ---------------------------------------------------------------------------

def probe_ui(nx, session):
    # v1.1 部件上下文兜底: NX10 实测无工作部件时 CreateDialog 报
    # "该操作只能对工作部件执行" —— 与 dlx 本身无关, 先补上下文
    try:
        if session.Parts.Work is None:
            session.Parts.NewDisplay("nx_probe_ui_ctx",
                                     nx.Part.Units.Millimeters)
    except Exception:
        pass
    try:
        ui = nx.UI.GetUI()
    except Exception as ex:
        for i in range(1, 6):
            add("UI%03d" % i, "UI", "(前置失败)", "SKIP",
                "UI.GetUI 失败: %s" % ex)
        return

    # 写两个 dlx 变体
    d = out_dir()
    paths = {}
    try:
        pa = os.path.join(d, "nx_probe_dlx_a.dlx")
        with io.open(pa, "w", encoding="utf-8") as f:
            f.write(build_probe_dlx(True))
        paths["A(NX=2312.0.0)"] = pa
        pb_ = os.path.join(d, "nx_probe_dlx_b.dlx")
        with io.open(pb_, "w", encoding="utf-8") as f:
            f.write(build_probe_dlx(False))
        paths["B(省略NX属性)"] = pb_
    except Exception as ex:
        for i in range(1, 6):
            add("UI%03d" % i, "UI", "(前置失败)", "SKIP",
                "dlx 写盘失败: %s" % ex)
        return

    loaded = None
    loaded_key = None
    dlg_by_key = {}
    for key in ("A(NX=2312.0.0)", "B(省略NX属性)"):
        rid = "UI002" if key.startswith("A") else "UI003"
        item = "CreateDialog 实载 dlx 变体%s" % key
        try:
            dlg = ui.CreateDialog(paths[key])
            dlg_by_key[key] = dlg
            add(rid, "UI", item, "AVAILABLE",
                "该版本可加载此 dlx 形式" + ("(2312 版本戳)" if key.startswith("A")
                                        else "(省略 NX 属性)"))
        except Exception as ex:
            add(rid, "UI", item, "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
    for key in ("A(NX=2312.0.0)", "B(省略NX属性)"):
        if key in dlg_by_key:
            loaded = dlg_by_key[key]
            loaded_key = key
            break
    if loaded is not None:
        if loaded_key.startswith("B") and "A(NX=2312.0.0)" not in dlg_by_key:
            add("UI003", "UI", "dlx 兼容结论", "INFO",
                "仅变体B可加载 → dlx 策略采用'unknown 时省略 NX 属性'")
        # UI001 handler 方法名
        names = ["AddDialogShownHandler", "AddShowHandler", "AddOkHandler",
                 "AddCancelHandler", "AddInitializeHandler", "AddUpdateHandler"]
        has = [n for n in names if hasattr(loaded, n)]
        lack = [n for n in names if n not in has]
        add("UI001", "UI", "Dialog 回调注册方法名", "INFO",
            "存在: %s | 缺失: %s" % (", ".join(has) or "无",
                                    ", ".join(lack) or "无"))
        # UI004 枚举 4 通道
        try:
            blk = loaded.TopBlock.FindBlock(ENUM_BLOCK_ID)
            rd_detail = []
            for kind in ("value", "setenum", "setenumstr", "setint"):
                props = None
                write_ok = False
                match = False
                got = None
                try:
                    if kind == "value":
                        blk.Value = 1
                    elif kind == "setenum":
                        props = blk.GetProperties()
                        props.SetEnum("Value", 1)
                    elif kind == "setenumstr":
                        props = blk.GetProperties()
                        props.SetEnumAsString("Value", ENUM_LABELS[1])
                    else:
                        props = blk.GetProperties()
                        props.SetInteger("Value", 1)
                    write_ok = True
                except Exception as ex:
                    rd_detail.append("%s: 写失败(%s)" % (kind, ex))
                finally:
                    if props is not None:
                        try:
                            props.Dispose()
                        except Exception:
                            pass
                if write_ok:
                    try:
                        got = int(blk.Value)
                    except Exception:
                        try:
                            got = blk.ValueAsString
                        except Exception:
                            got = "?"
                    match = (got == 1) or (got == ENUM_LABELS[1]) \
                        or (got == "1")
                    rd_detail.append("%s: 写OK 读回=%r 匹配=%s"
                                     % (kind, got, match))
            add("UI004", "UI", "枚举块 4 写入通道写+读回", "INFO",
               "; ".join(rd_detail))
        except Exception as ex:
            add("UI004", "UI", "枚举块 4 写入通道写+读回", "SKIP",
                "TopBlock.FindBlock 不可用(未 Launch 所致? 请在 NX 图形界面内复跑): %s" % ex)
        # UI005 DialogSizing
        try:
            tb = loaded.TopBlock
            gs = [m for m in ("GetDialogSizingMembers", "DialogSizingAsString")
                  if hasattr(tb, m)]
            add("UI005", "UI", "TopBlock DialogSizing 成员", "INFO",
                "存在: %s" % (", ".join(gs) if gs else "无(主脚本已守卫降级)"))
        except Exception as ex:
            add("UI005", "UI", "TopBlock DialogSizing 成员", "SKIP", "%s" % ex)
        for _k, d_ in dlg_by_key.items():
            try:
                d_.Dispose()
            except Exception:
                pass
    else:
        add("UI001", "UI", "Dialog 回调注册方法名", "SKIP", "两变体均未加载")
        add("UI004", "UI", "枚举块 4 写入通道写+读回", "SKIP", "两变体均未加载")
        add("UI005", "UI", "TopBlock DialogSizing 成员", "SKIP", "两变体均未加载")


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def write_outputs():
    d = out_dir()
    jpath = os.path.join(d, "nx_compat_probe.json")
    cpath = os.path.join(d, "nx_compat_probe.csv")
    meta = {"probe_version": PROBE_VERSION, "python": sys.version,
            "items": RESULTS}
    with io.open(jpath, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False, indent=1))
    try:
        with io.open(cpath, "w", encoding="utf-8-sig", newline="") as f:
            f.write("id,category,item,result,detail\r\n")
            for r in RESULTS:
                row = [r["id"], r["category"], r["item"], r["result"],
                       r["detail"].replace('"', '""')]
                f.write(",".join('"%s"' % c for c in row) + "\r\n")
    except Exception:
        pass
    return jpath, cpath


def main():
    print("=== NX 兼容性探针 v%s ===" % PROBE_VERSION)
    probe_py()

    nx = None
    session = None
    uf = None
    try:
        import NXOpen as nx
        session = nx.Session.GetSession()
        try:
            import NXOpen.UF
            uf = NXOpen.UF.UFSession.GetUFSession()
        except Exception as ex:
            add("VER000", "VER", "UFSession", "ERROR",
                "UF 不可用: %s —— UF 相关项跳过" % ex)
    except ImportError:
        add("VER001", "VER", "UF.AskVersion()", "SKIP", "无 NX 环境(裸 Python)")
        add("VER002", "VER", "环境变量 UGII_VERSION", "SKIP", "无 NX 环境")
        add("VER003", "VER", "环境变量 UGII_ROOT_DIR", "SKIP", "无 NX 环境")
        add("VER004", "VER", "环境变量 UGII_BASE_DIR/UGII_UG_DIR", "SKIP",
            "无 NX 环境")
        add("VER005", "VER", "NXOpen 模块路径版本解析(首选通道)", "SKIP",
            "无 NX 环境")
        for i in range(1, 26):
            add("API%03d" % i, "API", "NXOpen API", "SKIP", "无 NX 环境")
        for i in range(1, 7):
            add("MAR%03d" % i, "MAR", "数组参数编组", "SKIP", "无 NX 环境")
        for i in range(1, 6):
            add("UI%03d" % i, "UI", "BlockStyler", "SKIP", "无 NX 环境")

    if nx is not None:
        probe_ver(uf, session)
        try:
            probe_api(nx, session, uf)
        except Exception as ex:
            add("API999", "API", "API 组未捕获异常", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
        try:
            probe_ui(nx, session)
        except Exception as ex:
            add("UI999", "UI", "UI 组未捕获异常", "ERROR",
                "%s: %s" % (type(ex).__name__, ex))
        try:
            session.ListingWindow.Open()
            for r in RESULTS:
                session.ListingWindow.WriteLine(
                    "[%s] %s %s: %s %s" % (r["id"], r["category"], r["item"],
                                           r["result"], r["detail"]))
        except Exception:
            pass

    jpath, cpath = write_outputs()
    n_av = sum(1 for r in RESULTS if r["result"] == "AVAILABLE")
    n_mi = sum(1 for r in RESULTS if r["result"] == "MISSING")
    n_er = sum(1 for r in RESULTS if r["result"] == "ERROR")
    n_sk = sum(1 for r in RESULTS if r["result"] in ("SKIP", "INFO"))
    print("=== 完成: AVAILABLE=%d MISSING=%d ERROR=%d SKIP/INFO=%d ==="
          % (n_av, n_mi, n_er, n_sk))
    print("JSON: %s" % jpath)
    print("CSV : %s" % cpath)


if __name__ == "__main__":
    main()
