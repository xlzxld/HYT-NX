# -*- coding: utf-8 -*-
"""nx_extrude_runner.py — NX 分层拉伸自动化（CAD DXF → 3D）  v1.40  2026-09-02

重构说明:
  本文件作为向后兼容门面 (Facade)，向外部保留全部历史公共与私有符号 API。
  核心逻辑已模块化拆分至 cad3d/ 包:
    - cad3d.core: 路径、配置、常量、日志与状态管理
    - cad3d.geom: 几何实体、DXF 解析、拓扑环链与评估断言
    - cad3d.modeling: NXOpen 跨版本适配、图层拉伸、标准件装配与 JRT 加热条
    - cad3d.ui: Block UI Styler XML 动态生成与三段式交互对话框
    - cad3d.pipeline: 主流水线编排与批处理冒烟套件
    - cad3d.selftest: 离线自测套件与合成 DXF 生成器
"""

import io
import os
import sys

# ----------------------------------------------------------------------------
# NX Journal 解释器持久化缓存驱逐: 确保每次播放日记都重新加载 cad3d 包代码
# ----------------------------------------------------------------------------
for _mod in list(sys.modules.keys()):
    if _mod == "cad3d" or _mod.startswith("cad3d."):
        del sys.modules[_mod]

# ============================================================================
# 显式符号重导出 (严格兼容外部脚本并满足 AST 静态检查)
# ============================================================================

from cad3d.core.constants import (
    SCRIPT_VERSION, FEATURE_PREFIX, COMP_PREFIX, LOOP_TOL, CHAIN_TOL,
    _LAYER_DEFS, _NX_LAYER_START, _LAYER_DISTS, LAYER_TABLE, LAYER_CODES,
    REF_LAYER_TABLE, DYNAMIC_START, MANAGED_MIN, MANAGED_MAX, assign_layers,
    TARGET_CODE, DIALOG_GROUPS, _LINK_OFFSETS_RAW, _LINK_OFFSETS, LINK_RULES,
    JRT_FROM_TOP, _JT_LINK_FALLBACK, JT_LINK_MODES, JT_LINK_DEFAULT,
    JT_LINK_OPTS, _CX_LINK_END_OFF, STDPARTS_DIRNAME, DEFAULT_STD_RULE,
    DEFAULT_JRT, _ZMODE_FALLBACK, _ZMODE_DEFS, ZMODE_OPTS, BOOL_OPTS,
    DIR_OPTS, LAYER_SEL_OPTS, JRT_FIELDS, STD_MAX_ANCHORS
)

from cad3d.core.paths import (
    ROOT_DIR, script_dir, _logs_dir, _fresh_dlx_path, _temp_dlx_path,
    stdparts_dir, _json_path, resolve_dxf_path
)

from cad3d.core.config import (
    _CFG_NOTES, _note, _cfg_num, _cfg_int, _cfg, _import_module_from_path,
    _load_user_config, _USER_CFG, SCHEMA_VERSION, _JRT_BLEND_R, _JRT_R_STEP,
    _JRT_R_MIN
)

from cad3d.core.logging import (
    _fmt_num, Log
)

from cad3d.core.state import (
    _jt_link_values, jt_mode_with_memory, _cx_link_values, derive_linked,
    jrt_with_memory, default_params, load_state, _name_list, save_state,
    merge_params, merge_jrt
)

from cad3d.geom.entities import (
    DXLine, DXArc, DXCircle
)

from cad3d.geom.dxf_parser import (
    _read_dxf_text, entities_of, parse_dxf
)

from cad3d.geom.topo import (
    _pkey, _near_keys, find_chains, loop_polygon, poly_area, _bbox,
    point_in_poly, _loop_in_loop, organize_loops, _chain_tips, _cluster_tips,
    _merge_open_chains, _center_seen, collect_circle_anchors,
    _chain_outlet_mids, _chain_connectors
)

from cad3d.geom.eval import (
    _q, _nx_curve_fp, _dxf_ent_fp, dxf_fingerprints, _faces_healthy,
    _flush_start_r, _dome_body_ok, _blend_ok, _conn_face_pick, _jrt_sides
)

from cad3d.modeling.nx_compat import (
    MARK_ATTR, _set_expr, _mark_curve, _is_marked, _iter, _bodies_of,
    _matrix3x3
)

from cad3d.modeling.purge import (
    _CREATED_FEATURES, nx_purge, clean_previous, ensure_categories
)

from cad3d.modeling.std_rules import (
    _std_z, std_part_defaults, guess_std_rule, sanitize_std_rule,
    _rule_usable, _unusable_names, discover_std_parts, merge_std_rules,
    anchors_overflow
)

from cad3d.modeling.extrude import (
    create_curves, _create_curves, work_part_rules, _add_to_section_compat,
    _sc_rule_options, extrude_curves, modeling_ents, build_layer
)

from cad3d.modeling.stdparts import (
    _place_delta, _pick_target, _promote_body, _bool_one, _bool_feature,
    _remove_parameters, _usable_parts, place_std_parts
)

from cad3d.modeling.jrt import (
    _uf_face_data, _find_flat_face, _edge_blend_end, _body_face_rows,
    _body_volume, _edge_blend_end_retry, _delete_faces, _delete_faces_safe,
    _pick_conn_faces, _set_display, build_jrt
)

from cad3d.modeling.display import (
    _refresh_display
)

from cad3d.ui.dlx_builder import (
    _esc, _blk_double, _blk_label, _blk_button, _blk_filebrowser,
    _blk_enum, _blk_toggle, _group_item, build_selection_dlx, _opt_index,
    build_dlx, build_std_dlx, write_std_dlx, write_dlx
)

from cad3d.ui.dialogs import (
    _dlg_show, SelectionDialog, _BlockDialogBase, ParamDialog,
    StdParamsDialog
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
    _undefined_name_check, selftest
)


def main():
    argv = [a for a in sys.argv[1:] if not a.endswith(".py")]
    if "--selftest" in argv:
        i = argv.index("--selftest")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        sys.exit(0 if selftest(arg) else 1)
    if "--make-sample-dxf" in argv:
        i = argv.index("--make-sample-dxf")
        out = argv[i + 1] if i + 1 < len(argv) else os.path.join(
            script_dir(), "sample_layers.dxf")
        make_sample_dxf(out)
        print("sample dxf -> %s" % out)
        return

    # 以下需要 NX 环境
    try:
        import NXOpen  # noqa: F401
    except ImportError:
        print("本脚本需要在 NX 中运行(工具→日记→播放), "
              "或用 --selftest / --make-sample-dxf 做无 NX 自测。")
        return

    if "--batch" in argv:
        i = argv.index("--batch")
        arg = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else None
        batch_run(arg)
        return

    # 常规: 三段式 —— ①标准件选择(有件才弹; 取消=中止) ②主参数(OK只收集) ③标准件参数(执行)
    theSession = NXOpen.Session.GetSession()
    if theSession.Parts.Work is None:
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Warning,
            "请先新建或打开一个部件(需要工作部件)。")
        return

    if _CFG_NOTES:
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D 配置提示", NXOpen.NXMessageBox.DialogType.Warning,
            "\n".join(_CFG_NOTES))

    state = load_state()
    params = merge_params(state)
    std_rules_all = merge_std_rules(state)
    jrt = merge_jrt(state)

    # 第一段: 标准件选择(记忆上次选择; 新件默认不勾; 无件跳过)
    selected = None
    if std_rules_all:
        saved_sel = (state.get("selected")
                     if state.get("schema") == SCHEMA_VERSION else None)
        if saved_sel is None:
            saved_sel = []
        elif not isinstance(saved_sel, (list, tuple)):
            saved_sel = []
        else:
            saved_sel = [f for f in saved_sel
                         if f in std_rules_all
                         and _rule_usable(std_rules_all[f])]
        sel_dlx_path = _fresh_dlx_path("nx_std_select")
        try:
            with io.open(sel_dlx_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_selection_dlx(sorted(std_rules_all), saved_sel))
        except IOError:
            sel_dlx_path = None
        if not (sel_dlx_path and os.path.isfile(sel_dlx_path)):
            selected = [f for f in sorted(std_rules_all)
                        if f in set(saved_sel)
                        and _rule_usable(std_rules_all[f])]
            if not selected:
                selected = [f for f in sorted(std_rules_all)
                            if _rule_usable(std_rules_all[f])]
        else:
            seldlg = None
            try:
                seldlg = SelectionDialog(sel_dlx_path,
                                         sorted(std_rules_all), saved_sel)
                selected = seldlg.Launch()
            except Exception as ex:
                NXOpen.UI.GetUI().NXMessageBox.Show(
                    "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                    "选择对话框启动失败: %s" % ex)
                return
            finally:
                if seldlg is not None:
                    seldlg.Dispose()
            if selected is None:
                return
            save_state(state.get("dxf_path") or resolve_dxf_path(state),
                       params, std_rules_all, selected=selected,
                       jrt_se=(state.get("jrt_se")
                               if state.get("schema") == SCHEMA_VERSION
                               else None),
                       jt_link_mode=(state.get("jt_link_mode")
                                     if state.get("schema") == SCHEMA_VERSION
                                     else None))
        std_rules = {f: std_rules_all[f] for f in selected}
    else:
        std_rules = {}

    # 第二段: 主参数窗口(FLB/图层/JRT; 无标准件组; OK 只收集不执行)
    dlx = write_dlx(params, jrt, jt_mode_with_memory(state))
    if not dlx:
        NXOpen.UI.GetUI().NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Error, ".dlx 对话框文件生成失败。")
        return

    dlg = None
    try:
        dlg = ParamDialog(dlx, std_rules=None, selected=selected,
                          execute_on_ok=False)
        dlg.Launch()
    except Exception as ex:
        try:
            import tempfile
            dlx2 = _fresh_dlx_path("nx_extrude_runner",
                                   base_dir=tempfile.gettempdir())
            with io.open(dlx2, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_dlx(params, jrt,
                        jt_mode_with_memory(state)))
            dlg = ParamDialog(dlx2, std_rules=None, selected=selected,
                              execute_on_ok=False)
            dlg.Launch()
        except Exception as ex2:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                "对话框启动失败:\n%s\n\n(回退也失败: %s)" % (ex, ex2))
            return
    finally:
        if dlg is not None:
            dlg.Dispose()
    if dlg is None or dlg.result_params is None:
        return
    params2 = dlg.result_params
    jrt2 = dlg.result_jrt
    dxf2 = dlg.result_dxf
    mode2 = dlg.result_mode or jt_mode_with_memory(state)

    try:
        save_state(dxf2 or resolve_dxf_path(state), params2, std_rules_all,
                   selected=selected,
                   jrt_se=[float(jrt2.get("start", 0.0)),
                           float(jrt2.get("end", 0.0))],
                   jt_link_mode=mode2)
    except (TypeError, ValueError):
        pass

    # 第三段: 标准件参数窗口(每件一个可收起组; OK/Apply 执行; 取消=中止)
    if std_rules:
        sdx = write_std_dlx(std_rules, params2)
        if not sdx:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
                "标准件参数 .dlx 生成失败。")
            return
        sdlg = None
        try:
            sdlg = StdParamsDialog(sdx, std_rules, params2, jrt2, dxf2,
                                   selected, std_rules_all=std_rules_all,
                                   jt_mode=mode2)
            sdlg.Launch()
        except Exception as ex:
            NXOpen.UI.GetUI().NXMessageBox.Show(
                "CAD3D", NXOpen.NXMessageBox.DialogType.Error,
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
