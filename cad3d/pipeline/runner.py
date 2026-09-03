# -*- coding: utf-8 -*-
"""cad3d.pipeline.runner —— 主流水线控制、阶段编排与最终执行。"""

import os
import traceback

from cad3d.core.constants import (
    SCRIPT_VERSION, LAYER_TABLE, LAYER_CODES, TARGET_CODE, assign_layers
)
from cad3d.core.config import _CFG_NOTES
from cad3d.core.paths import resolve_dxf_path
from cad3d.core.logging import Log
from cad3d.core.state import (
    load_state, save_state, merge_jrt
)
from cad3d.modeling.std_rules import merge_std_rules
from cad3d.geom.dxf_parser import parse_dxf
from cad3d.modeling.purge import nx_purge, ensure_categories
from cad3d.modeling.extrude import create_curves, build_layer
from cad3d.modeling.stdparts import _usable_parts, place_std_parts, _remove_parameters
from cad3d.modeling.jrt import build_jrt
from cad3d.modeling.display import _refresh_display


def run_pipeline(dxf_path, params, session=None, work_part=None, log=None,
                 std_rules=None, jrt=None):
    """主流水线: 清理 → 建曲线 → 分层拉伸/布尔。返回 (ok, stats)。"""
    import NXOpen as _nx
    import NXOpen.Features
    import NXOpen.GeometricUtilities

    if session is None:
        session = _nx.Session.GetSession()
    if work_part is None:
        work_part = session.Parts.Work
    if log is None:
        log = Log(session)
    stats = {}

    if work_part is None:
        log("【错误】未找到有效的工作部件(Work Part is None), 中止。")
        return False, stats

    log("")
    log("================ NX 分层拉伸 v%s ================" % SCRIPT_VERSION)
    for _note in _CFG_NOTES:
        log("【配置提示】%s" % _note)
    log("【输入】图纸: %s" % dxf_path)
    if not dxf_path or not os.path.isfile(dxf_path):
        log("【错误】未找到图纸文件, 中止。")
        return False, stats

    actual_dxf = dxf_path
    is_temp_dxf = False
    if dxf_path.lower().endswith(".dwg"):
        from cad3d.geom.dwg_converter import convert_dwg_to_dxf
        try:
            actual_dxf = convert_dwg_to_dxf(dxf_path, log=log)
            is_temp_dxf = True
        except Exception as ex:
            log("【错误】DWG 转 DXF 失败: %s" % ex)
            try:
                _nx.UI.GetUI().NXMessageBox.Show(
                    "CAD3D", _nx.NXMessageBox.DialogType.Error, str(ex))
            except Exception:
                pass
            return False, stats

    mark = session.SetUndoMark(_nx.Session.MarkVisibility.Visible, "CAD3D 分层拉伸")
    try:
        layers, dstats = parse_dxf(actual_dxf)
        if dstats["ref_layers"]:
            log("【解析】参考图层(导入不建模): %s" % ", ".join(
                "%s×%d" % kv for kv in sorted(dstats["ref_layers"].items())))
        if dstats["unsupported"]:
            _uns = ", ".join("%s×%d" % kv
                             for kv in sorted(dstats["unsupported"].items()))
            log("【解析】警告: 不支持的实体类型已跳过: %s" % _uns)
            if dstats.get("unsupported_model"):
                log("【警告】建模图层上有 %d 个不支持的实体(多为 LWPOLYLINE"
                    "多段线), 对应轮廓不会建模——请在 AutoCAD 用 EXPLODE "
                    "炸开成直线/圆弧后重试。" % dstats["unsupported_model"])
                try:
                    _nx.UI.GetUI().NXMessageBox.Show(
                        "CAD3D 解析警告", _nx.NXMessageBox.DialogType.Warning,
                        "DXF 建模图层上有 %d 个不支持的实体(%s)。\n"
                        "对应轮廓不会建模——请回 AutoCAD 把多段线 EXPLODE "
                        "炸开成直线/圆弧后重跑。"
                        % (dstats["unsupported_model"], _uns))
                except Exception:
                    pass
        if dstats["nonplanar"]:
            log("【解析】警告: %d 个实体 Z≠0, 已按 Z=0 处理。" % dstats["nonplanar"])
        log("【解析】共 %d 个实体, 目标图层: %s" % (
            dstats["total"],
            ", ".join("%s×%d" % (c, len(layers.get(c) or [])) for c in LAYER_CODES)))

        nx_purge(session, work_part, log, dxf_layers=layers)

        layer_map = assign_layers(list(layers.keys()), work_part=work_part, log=log)
        ensure_categories(work_part, layer_map, log)
        nx_curves = create_curves(work_part, layers, layer_map, log)

        order = [TARGET_CODE] + [r[0] for r in LAYER_TABLE if r[5] == "none"] \
                + [r[0] for r in LAYER_TABLE if r[5] == "subtract"]
        flb_regions = []
        for code in order:
            matches = [r for r in LAYER_TABLE if r[0] == code]
            if not matches:
                continue
            row = matches[0]
            _code, zh, _num, _s, _e, role = row
            _bodies, regions = build_layer(session, work_part, code, zh, role,
                                           layers, nx_curves, params, flb_regions,
                                           log, stats)
            if code == TARGET_CODE:
                flb_regions = regions
        if not flb_regions:
            subs = ",".join(r[0] for r in LAYER_TABLE if r[5] == "subtract")
            log("【警告】FLB 基准体未生成, %s 等布尔减层的轮廓将按普通体保留。" % subs)

        if std_rules is None:
            std_rules = merge_std_rules(load_state())
        if std_rules:
            usable, _unref = _usable_parts(std_rules, log)
            place_std_parts(session, work_part, layers, flb_regions, params,
                            usable, log, stats=stats)

        if jrt is None:
            jrt = merge_jrt(load_state())
        build_jrt(session, work_part, layers, nx_curves, flb_regions, params,
                  jrt, log, stats)

        bodies, seen = [], set()
        for body, _bb in flb_regions:
            if body is not None and id(body) not in seen:
                seen.add(id(body))
                bodies.append(body)
        for code in list(LAYER_CODES) + ["JRT", "STD"]:
            for body in (stats.get(code, {}).get("bodies") or []):
                if body is not None and id(body) not in seen:
                    seen.add(id(body))
                    bodies.append(body)
        _remove_parameters(session, work_part, bodies, log)

        nfeat = sum(v.get("features", 0) for v in stats.values())
        log("【完成】特征 %d 个。各图层: %s" % (
            nfeat, "; ".join("%s 曲线%d/轮廓%d/%s" % (
                c, stats[c]["curves"], stats[c]["profiles"], stats[c]["note"] or "OK")
                for c in list(LAYER_CODES) + ["JRT", "STD"] if c in stats)))
        _refresh_display(session, work_part, log)
        return True, stats
    except Exception as ex:
        log("【错误】%s" % ex)
        log("【堆栈】%s" % traceback.format_exc())
        try:
            session.UndoToMark(mark, "CAD3D 出错回滚")
            log("【回滚】已撤销本次全部改动。")
        except Exception as ex2:
            log("【回滚失败】%s" % ex2)
        try:
            _nx.UI.GetUI().NXMessageBox.Show(
                "CAD3D 分层拉伸", _nx.NXMessageBox.DialogType.Error, str(ex))
        except Exception:
            pass
        return False, stats
    finally:
        if is_temp_dxf and actual_dxf and os.path.isfile(actual_dxf):
            try:
                os.remove(actual_dxf)
                log("【DWG 转换】临时 DXF 文件已安全移除清理。")
            except Exception as ex_del:
                log("【DWG 转换】清理临时文件提示: %s" % ex_del)


def execute_pipeline(dxf, params, jrt, std_rules, session,
                     std_rules_all=None, selected=None, ui=None,
                     jt_link_mode=None):
    """三段式最终执行: 校验图纸 → 保存 JSON(全部规则+选中清单) → run_pipeline。"""
    import NXOpen

    if not dxf or not os.path.isfile(dxf):
        dxf = resolve_dxf_path({"dxf_path": dxf})
    if not dxf or not os.path.isfile(dxf):
        if ui is None:
            ui = NXOpen.UI.GetUI()
        ui.NXMessageBox.Show(
            "CAD3D", NXOpen.NXMessageBox.DialogType.Warning,
            "未找到有效的图纸文件 (DWG/DXF)。\n请在主参数窗口顶部选择图纸文件,\n"
            "或把图纸放到脚本同目录后重试。")
        return False
    full_rules = dict(std_rules_all or {})
    full_rules.update(std_rules or {})
    p_dict = params if isinstance(params, dict) else {}
    j_dict = jrt if isinstance(jrt, dict) else {}
    save_state(dxf, {k: list(v) for k, v in p_dict.items()}, full_rules,
               selected=selected,
               jrt_se=[j_dict.get("start", 0.0), j_dict.get("end", 0.0)],
               jt_link_mode=jt_link_mode)
    ok, _stats = run_pipeline(dxf, p_dict, session=session,
                              work_part=session.Parts.Work,
                              log=Log(session), std_rules=std_rules, jrt=j_dict)
    return ok
