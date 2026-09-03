# -*- coding: utf-8 -*-
"""
nx_extrude_runner.py —— CAD3D 分层拉伸与自动化建模主入口 (v2.2 定版)
=============================================================================
适用环境：Siemens NX 10 / NX 12 / NX 2312 及以上版本（Python 3.3 ~ 3.12+）
最后更新：2026-09-03

【模块职责】
  1. 作为 NX 日记播放（Tools -> Journal -> Play）的统一主入口；
  2. 提供三段式人机交互向导：
     - 第一段：标准件装配清单勾选（记忆上次选择，新件默认关闭）；
     - 第二段：分层拉伸尺寸与 JRT 加热条主参数配置（实时联动）；
     - 第三段：各标准件参数微调并驱动全自动拉伸、装配与型腔布尔运算；
  3. 提供命令行无头运行模式：--selftest（离线自测）、--batch（批量处理）、--make-sample-dxf；
  4. 作为兼容门面 (Facade)，向外部测试脚本与工具暴露必要的稳定 API。
=============================================================================
"""

import io
import os
import sys

# ----------------------------------------------------------------------------
# 运行时环境配置与绝对路径自适应引导（确保在任意外部工作目录/NX日记播放均能正确定位）
# ----------------------------------------------------------------------------
sys.dont_write_bytecode = True
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ----------------------------------------------------------------------------
# NX Journal 解释器持久化缓存驱逐（确保每次播放日记都重新加载 cad3d 核心代码）
# ----------------------------------------------------------------------------
for _mod in list(sys.modules.keys()):
    if _mod == "cad3d" or _mod.startswith("cad3d."):
        del sys.modules[_mod]

# ============================================================================
# 模块符号导出 (精炼梳理：核心公共 API + 外部工具兼容依赖)
# ============================================================================

# 1. 核心公共 API 与系统常量
from cad3d.core.constants import (
    SCRIPT_VERSION, FEATURE_PREFIX, COMP_PREFIX, TARGET_CODE,
    LOOP_TOL, CHAIN_TOL, STD_MAX_ANCHORS, DEFAULT_JRT, DEFAULT_STD_RULE
)
from cad3d.core.paths import (
    ROOT_DIR, script_dir, stdparts_dir, resolve_dxf_path, _fresh_dlx_path
)
from cad3d.core.config import (
    SCHEMA_VERSION, _CFG_NOTES
)
from cad3d.core.logging import (
    Log
)
from cad3d.core.state import (
    load_state, save_state, default_params, merge_params,
    merge_jrt, jt_mode_with_memory
)
from cad3d.geom.dxf_parser import (
    parse_dxf
)
from cad3d.pipeline.runner import (
    run_pipeline, execute_pipeline
)
from cad3d.pipeline.batch import (
    batch_run
)
from cad3d.selftest.sample_dxf import (
    make_sample_dxf
)
from cad3d.selftest.suite import (
    selftest
)

# 2. 外部脚本与辅助工具兼容符号 (满足 test/*, batch_smoke 与 tools/nx_zero_ref.py)
from cad3d.modeling.std_rules import (
    guess_std_rule, sanitize_std_rule, _rule_usable, merge_std_rules
)
from cad3d.modeling.nx_compat import (
    _is_marked, _matrix3x3
)
from cad3d.modeling.stdparts import (
    _promote_body, _remove_parameters
)
from cad3d.geom.topo import (
    collect_circle_anchors
)
from cad3d.ui.dlx_builder import (
    build_selection_dlx, build_dlx, write_dlx, write_std_dlx
)
from cad3d.ui.dialogs import (
    SelectionDialog, ParamDialog, StdParamsDialog
)


# ============================================================================
# 主执行入口 (三段式交互流程编排与命令行调度)
# ============================================================================

def main():
    """主程序入口：解析命令行参数或启动 NX 交互三段式对话框流程。"""
    argv = [a for a in sys.argv[1:] if not a.endswith(".py")]

    # ─── 命令行工具分发 ───────────────────────────────────────────────────────
    if "--selftest" in argv:
        i = argv.index("--selftest")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        sys.exit(0 if selftest(arg) else 1)

    if "--make-sample-dxf" in argv:
        i = argv.index("--make-sample-dxf")
        out = argv[i + 1] if i + 1 < len(argv) else os.path.join(script_dir(), "sample_layers.dxf")
        make_sample_dxf(out)
        print("sample dxf -> %s" % out)
        return

    # ─── NX 运行环境校验 ──────────────────────────────────────────────────────
    try:
        import NXOpen  # noqa: F401
    except ImportError:
        print("本脚本需要在 Siemens NX 中运行(工具 -> 日记 -> 播放), "
              "或使用 --selftest / --make-sample-dxf 进行离线验证。")
        return

    if "--batch" in argv:
        i = argv.index("--batch")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        batch_run(arg)
        return

    theSession = NXOpen.Session.GetSession()
    theUI = NXOpen.UI.GetUI()

    # 检查是否存在活动的工作部件
    if theSession.Parts.Work is None:
        theUI.NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Warning,
            "请先新建或打开一个部件（操作需要有效的工作部件）。")
        return

    # 提示配置加载警告（若有非法配置或回退项）
    if _CFG_NOTES:
        theUI.NXMessageBox.Show(
            "CAD3D 配置提示", NXOpen.NXMessageBox.DialogType.Warning,
            "\n".join(_CFG_NOTES))

    # ─── 加载运行时历史记忆与合并默认配置 ──────────────────────────────────────
    state = load_state()
    params = merge_params(state)
    std_rules_all = merge_std_rules(state)
    jrt = merge_jrt(state)

    # ─── 第一段：标准件装配清单选择窗口 ────────────────────────────────────────
    # 功能：仅在存在可用标准件时弹出；记忆上次勾选项；未勾选或取消则不执行标准件装配
    selected = None
    if std_rules_all:
        saved_sel = (state.get("selected") if state.get("schema") == SCHEMA_VERSION else None)
        if not isinstance(saved_sel, (list, tuple)):
            saved_sel = []
        else:
            saved_sel = [f for f in saved_sel if f in std_rules_all and _rule_usable(std_rules_all[f])]

        sel_dlx_path = _fresh_dlx_path("nx_std_select")
        try:
            with io.open(sel_dlx_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_selection_dlx(sorted(std_rules_all), saved_sel))
        except IOError:
            sel_dlx_path = None

        if not (sel_dlx_path and os.path.isfile(sel_dlx_path)):
            selected = [f for f in sorted(std_rules_all) if f in set(saved_sel) and _rule_usable(std_rules_all[f])]
            if not selected:
                selected = [f for f in sorted(std_rules_all) if _rule_usable(std_rules_all[f])]
        else:
            seldlg = None
            try:
                seldlg = SelectionDialog(sel_dlx_path, sorted(std_rules_all), saved_sel)
                selected = seldlg.Launch()
            except Exception as ex:
                theUI.NXMessageBox.Show("CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                                        "标准件选择对话框启动失败: %s" % ex)
                return
            finally:
                if seldlg is not None:
                    seldlg.Dispose()

            if selected is None:
                return  # 用户在窗口①点击取消，中止整个流程

            # 保存当前选择到状态
            save_state(state.get("dxf_path") or resolve_dxf_path(state),
                       params, std_rules_all, selected=selected,
                       jrt_se=(state.get("jrt_se") if state.get("schema") == SCHEMA_VERSION else None),
                       jt_link_mode=(state.get("jt_link_mode") if state.get("schema") == SCHEMA_VERSION else None))

        std_rules = {f: std_rules_all[f] for f in selected}
    else:
        std_rules = {}

    # ─── 第二段：主参数配置窗口 (分层拉伸尺寸与 JRT 工艺参数) ──────────────────
    # 功能：收集分层拉伸起止值、DXF 图纸路径、JRT 参数与假体联动模式；点击 OK 仅收集数据
    dlx = write_dlx(params, jrt, jt_mode_with_memory(state))
    if not dlx:
        theUI.NXMessageBox.Show("CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                                ".dlx 对话框文件生成失败。")
        return

    dlg = None
    try:
        dlg = ParamDialog(dlx, std_rules=None, selected=selected, execute_on_ok=False)
        dlg.Launch()
    except Exception as ex:
        theUI.NXMessageBox.Show("CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                                "参数设置对话框启动失败: %s" % ex)
        return
    finally:
        if dlg is not None:
            dlg.Dispose()

    if dlg is None or dlg.result_params is None:
        return  # 用户在窗口②点击取消，中止流程

    params2 = dlg.result_params
    jrt2    = dlg.result_jrt
    dxf2    = dlg.result_dxf
    mode2   = dlg.result_mode or jt_mode_with_memory(state)

    # 实时持久化窗口②调整后的最新数据
    try:
        save_state(dxf2 or resolve_dxf_path(state), params2, std_rules_all,
                   selected=selected,
                   jrt_se=[float(jrt2.get("start", 0.0)), float(jrt2.get("end", 0.0))],
                   jt_link_mode=mode2)
    except (TypeError, ValueError):
        pass

    # ─── 第三段：标准件参数微调与建模执行 ──────────────────────────────────────
    # 功能：若勾选了标准件，弹窗供用户逐件微调参数，点击 Apply/OK 执行完整流水线；
    #       若未选择任何标准件，直接执行纯分层拉伸流水线。
    if std_rules:
        sdx = write_std_dlx(std_rules, params2)
        if not sdx:
            theUI.NXMessageBox.Show("CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                                    "标准件参数 .dlx 生成失败。")
            return
        sdlg = None
        try:
            sdlg = StdParamsDialog(sdx, std_rules, params2, jrt2, dxf2,
                                   selected, std_rules_all=std_rules_all,
                                   jt_mode=mode2)
            sdlg.Launch()
        except Exception as ex:
            theUI.NXMessageBox.Show("CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                                    "标准件参数对话框启动失败: %s" % ex)
        finally:
            if sdlg is not None:
                sdlg.Dispose()
    else:
        execute_pipeline(dxf2, params2, jrt2, {}, theSession,
                         std_rules_all=std_rules_all, selected=selected or [],
                         jt_link_mode=mode2)


if __name__ == "__main__":
    main()
