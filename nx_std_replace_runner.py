# -*- coding: utf-8 -*-
"""
nx_std_replace_runner.py —— 一键替换标准件（你指定换哪个）NX 日记入口 (v2.1)
=============================================================================
适用环境：Siemens NX 10 / NX 12 / NX 2312 及以上版本
播放方式：NX 菜单 工具 → 日记 → 播放，选本文件。
【本脚本】把模型里已放好的标准件换成你指定的另一个规格，没指定的不动。

【前提】已用 nx_extrude_runner.py 跑完分层拉伸并放好标准件；本脚本只动标准件，
  不建曲线、不拉伸、不碰分流板几何。

【第一页 = 指定替换关系】左边列出"模型里当前实际存在"的标准件（靠体上的
  CAD3D_TYPE 标记认，没有标记的东西一律不碰），右边挑要换成哪个规格；
  留在"不替换"上的整件保持原样。上次选过的映射记在记忆里、下次自动回填。

【位置怎么定 —— 反推锚点，默认不碰图纸】
  标准件全都做过归零（tools/nx_zero_ref.py：把定位点平移到零件原点，所以
  ref 全是 [0,0,0]），放置又是纯平移（pos = 锚点）。由此拿件里**任意一个**
  实体都能反推出同一个锚点：
      锚点 = 该体世界中心 − R · 该体零件局部中心
  同一件的多个实体各推一次，推出来的必须是**同一个点** —— 这份互相印证既是
  归组的依据（治"一个件被放成好几个"），也是正确性自检（比按容差猜可靠）。
  只有以下两种情况才回退去读图纸（图纸来源：记忆 → logs 缓存 → 弹窗手选）：
    · 件里有两个实体包围盒尺寸完全相同，认不清谁是谁；
    · 压线板(YXB)这类要靠图上定位线算摆向的件（反推给不出角度）。
  **一旦用到图纸，日期志与弹窗都会明确提示**，方便统计到底还需不需要图纸。

【产出】换完的件与主脚本产物同款：普通实体（已清掉建模步骤，不是提升体）。
【记忆】读图纸路径/每件参数/上次映射；只回写"映射"这一项，不动主脚本的参数。
【产出判读】控制台最后一行 + logs/std_replace_report.txt:
  REPLACE RESULT ok=True pairs=N old=X new=Y skip=S used_dxf=D
=============================================================================
"""

import functools
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

from cad3d.core.constants import LAYER_CODES, SCRIPT_VERSION, TARGET_CODE
from cad3d.core.logging import Log
from cad3d.core.paths import _logs_dir, stdparts_dir
from cad3d.core.state import default_params, load_state, save_replace_map
from cad3d.geom.dxf_parser import parse_dxf
from cad3d.geom.topo import collect_circle_anchors
from cad3d.modeling.display import _refresh_display
from cad3d.modeling.std_rules import (
    _rule_usable,
    guess_std_rule,
    merge_std_rules,
    sanitize_std_rule,
)
from cad3d.modeling.stdparts import (
    _batch_delete,
    _remove_parameters,
    place_std_parts,
    read_local_bodies,
    scan_model_bodies,
    snap_bodies_to_anchors,
    solve_placements,
)
from cad3d.ui.dialogs import DxfPickDialog, ReplaceMapDialog, StdParamsDialog
from cad3d.ui.dlx_builder import (
    write_dxf_pick_dlx,
    write_replace_map_dlx,
    write_std_dlx,
)

# DWG→DXF 转换缓存的文件名前缀(与 cad3d.geom.dwg_converter 一致)
_DWG_CACHE_PREFIX = "_dwg_cache_"

# 靠图上定位线/逐板判向放的图层: 反推锚点给不出摆向, 必须走图纸
_ANGLE_LAYERS = ("YXB",)


def _save_report(name, lines):
    """运行日志落盘 logs/<name>(与 nx_mold_cut_runner 同惯例)。"""
    p = os.path.join(_logs_dir(), name)
    try:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("report -> %s" % p)
    except OSError as ex:
        print("report 写入失败: %s" % ex)
    return p


def _cache_candidates():
    """logs/ 下全部 DWG 转换缓存 DXF, 按修改时间从新到旧。

    为什么不直接用 dwg_converter.lookup_dwg_cache: 那个接口要先对**原 dwg
    文件**做 stat 才能算出缓存键, 原图被移走/删掉就永远查不到; 这里直接扫目录,
    原图不在也能用上已经转好的图。
    """
    out = []
    try:
        names = os.listdir(_logs_dir())
    except OSError:
        return out
    for n in names:
        if not n.startswith(_DWG_CACHE_PREFIX) or not n.lower().endswith(".dxf"):
            continue
        p = os.path.join(_logs_dir(), n)
        try:
            if os.path.getsize(p) == 0:
                continue
            with open(p, "rb") as f:
                if b"SECTION" not in f.read(1024):
                    continue            # 半截/损坏的转换产物不进流水线
            out.append((os.path.getmtime(p), p))
        except OSError:
            continue
    out.sort(reverse=True)
    return [p for _m, p in out]


def _resolve_dxf(state, log, ui):
    """按优先级找图纸 → 可用路径 或 None(用户取消/都不行)。只在兜底时才调用。

    ① 记忆里的图纸还在: .dxf 直接用; .dwg 先查转换缓存、没有再转
    ② 记忆里的图纸没了: 扫 logs/ 下 _dwg_cache_*.dxf, 取最新的一张
    ③ 都没有: 弹窗让用户手动选一张
    """
    remembered = str((state or {}).get("dxf_path") or "")
    if remembered and os.path.isfile(remembered):
        if remembered.lower().endswith(".dwg"):
            from cad3d.geom.dwg_converter import convert_dwg_to_dxf
            try:
                p = convert_dwg_to_dxf(remembered, log=log)
                log("【图纸】用记忆里的 DWG 转出来的图: %s" % os.path.basename(p))
                return p
            except Exception as ex:
                log("【图纸】记忆里的 DWG 转换失败(%s), 改从 logs 缓存里找。" % ex)
        else:
            log("【图纸】用记忆里的图纸: %s" % remembered)
            return remembered
    elif remembered:
        log("【图纸】记忆里的图纸不在了(%s), 先从 logs 缓存里找。" % remembered)

    cands = _cache_candidates()
    if cands:
        log("【图纸】logs 下找到 %d 张转换缓存, 用最新的一张: %s"
            % (len(cands), os.path.basename(cands[0])))
        for c in cands[1:4]:
            log("        (另有: %s)" % os.path.basename(c))
        return cands[0]

    log("【图纸】logs 里也没有能用的图纸, 弹窗让你手动选。")
    pick_dlx = write_dxf_pick_dlx("上次的图纸找不到了: %s"
                                  % (remembered or "(记忆里没有)"))
    if not pick_dlx:
        log("【图纸】选择窗口文件生成失败, 中止。")
        return None
    dlg = None
    picked = None
    try:
        dlg = DxfPickDialog(pick_dlx)
        picked = dlg.Launch()
    except Exception as ex:
        log("【图纸】选择对话框启动失败: %s" % ex)
        return None
    finally:
        if dlg is not None:
            dlg.Dispose()
    if not picked:
        log("【图纸】没选图纸, 中止(模型一点没动)。")
        return None
    if picked.lower().endswith(".dwg"):
        from cad3d.geom.dwg_converter import convert_dwg_to_dxf
        try:
            return convert_dwg_to_dxf(picked, log=log)
        except Exception as ex:
            log("【图纸】DWG 转换失败: %s" % ex)
            return None
    log("【图纸】用你选的图纸: %s" % picked)
    return picked


def _scan_existing_std(rows):
    """扫描结果 → ({标准件文件名: [(体, 包围盒6), ...]}, 读不到盒的体数)。

    只认体上带 "STD:<文件名>" 标记的(主脚本放的件); 用户自己的图形没有标记,
    不会被卷进来。
    """
    out = {}
    n_nopos = 0
    for t, b, bb in rows or []:
        if not t.startswith("STD:"):
            continue
        if not bb:
            n_nopos += 1
            continue
        out.setdefault(t[4:], []).append((b, tuple(bb)))
    return out, n_nopos


def _bb_rows(items):
    """[(体, 包围盒6)] → [(尺寸3, 中心3)]。"""
    out = []
    for _b, bb in items:
        out.append(((bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]),
                    ((bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0,
                     (bb[2] + bb[5]) / 2.0)))
    return out


def _derive_anchors(session, work_part, old_fname, olds, log):
    """反推这个旧件的放置锚点(不需要图纸)。

    返回 (锚点XY列表, 参与替换的体下标列表, 失败原因);
    成功时原因为空, 失败时锚点列表为 None(调用方走图纸兜底)。
    """
    path = os.path.join(stdparts_dir(), old_fname)
    if not os.path.isfile(path):
        return None, [], "找不到 %s 这个件文件" % old_fname
    local = read_local_bodies(session, work_part, path, log)
    if not local:
        return None, [], "量不到这个件在零件坐标里的实体"
    rule = guess_std_rule(old_fname)
    flip = (str(rule.get("dir") or "+Z") == "-Z")
    got = solve_placements(local, _bb_rows(olds), flip=flip)
    if got["ambiguous"]:
        return None, [], "这个件里有包围盒尺寸完全相同的实体, 认不清谁是谁"
    if not got["anchors"]:
        return None, [], "反推不出可用的实例位置"
    if got["unmatched"]:
        return None, [], ("有 %d 个体没能和零件里的实体对上"
                          % len(got["unmatched"]))
    return ([(a[0], a[1]) for a in got["anchors"]], got["matched"], "")


def _measured_params(rows, log=None):
    """出厂默认参数 + 模型实测 Z 范围覆盖(替换流程没有第二页, 只能这么补)。

    Z 基准(FLB 顶/底、CX 顶)必须按模型实际高度算, 否则换上去的件会插到错误
    高度。体上量出来的 Z 范围与主流水线的 params 同源(拉伸体的起止值就是
    params 的起止值), 口径也一致: 大值=顶面、小值=底面。
    """
    params = default_params()
    zr = {}
    for t, _b, bb in rows:
        if bb is None or t.startswith("STD:"):
            continue
        cur = zr.get(t)
        if cur is None:
            zr[t] = [bb[2], bb[5]]
        else:
            cur[0] = min(cur[0], bb[2])
            cur[1] = max(cur[1], bb[5])
    for t, v in zr.items():
        params[t] = (v[0], v[1])
    if log is not None and zr:
        log("  实测高度: %s" % ", ".join("%s %.3f~%.3f" % (t, v[0], v[1])
                                        for t, v in sorted(zr.items())))
    return params


def _do_replace(session, work_part, mapping, rules, params, log, dxf_getter=None):
    """核心: 按用户指定的映射把旧规格换成新规格。返回结果字典(不抛异常)。

    只处理 mapping 里点名的旧件; 没点名的标准件一个都不动。
    定位优先"反推锚点", 失败才调 dxf_getter 去拿图纸(懒加载: 不用图纸时
    根本不碰图纸)。
    """
    import NXOpen

    st = {"ok": False, "pairs": 0, "old": 0, "new": 0, "skip": 0,
          "used_dxf": 0, "dxf_parts": []}
    rows = scan_model_bodies(work_part, log)
    existing, n_nopos = _scan_existing_std(rows)
    if n_nopos:
        log("【替换】提醒: 有 %d 个标准件体读不到位置(包围盒取不到), 不参与替换。"
            % n_nopos)
    if not existing:
        log("【替换】这个部件里没找到主脚本放的标准件(体上没有 CAD3D_TYPE 标记), "
            "中止。请先跑一次主脚本把件放好。")
        return st

    flb_regions = [(b, (bb[0], bb[1], bb[3], bb[4]))
                   for t, b, bb in rows if t == TARGET_CODE and bb]
    if not flb_regions:
        log("【替换】没找到分流板(FLB)实体: 需要挖孔的件只会放置、不挖孔。")

    dxf_cache = {"path": None, "layers": None}

    def _fallback_layers():
        """真要用图纸时才解析图纸(这就是"有没有用到图纸"的唯一入口)。"""
        if dxf_cache["layers"] is None:
            p = dxf_getter() if dxf_getter is not None else None
            if not p:
                return None
            layers_, dstats = parse_dxf(p)
            log("【图纸】解析到 %d 个图形; 各图层: %s"
                % (dstats["total"],
                   ", ".join("%s×%d" % (c, len(layers_.get(c) or []))
                             for c in LAYER_CODES)))
            dxf_cache["path"], dxf_cache["layers"] = p, layers_
        return dxf_cache["layers"]

    to_place, anchors_override, to_delete = {}, {}, []
    for old_fname in sorted(mapping):
        new_fname = mapping[old_fname]
        olds = existing.get(old_fname) or []
        if not olds:
            log("【替换】%s → %s: 模型里没有 %s, 跳过。"
                % (old_fname, new_fname, old_fname))
            st["skip"] += 1
            continue
        rule = sanitize_std_rule(rules.get(new_fname) or {})
        if not _rule_usable(rule):
            log("【替换】%s → %s: 新规格的参数没配好(缺参考点), 跳过。"
                % (old_fname, new_fname))
            st["skip"] += 1
            continue

        # ── ① 首选: 反推锚点(不需要图纸) ──────────────────────────────────
        need_dxf = str(rule.get("layer") or "").upper() in _ANGLE_LAYERS
        anchors_xy, use_idx = None, []
        if need_dxf:
            log("【替换】%s: 这类件要靠图上定位线定摆向, 直接走图纸。" % old_fname)
        else:
            anchors_xy, use_idx, why = _derive_anchors(
                session, work_part, old_fname, olds, log)
            if anchors_xy:
                log("【替换】%s: 反推出 %d 处实例位置(没用图纸)。"
                    % (old_fname, len(anchors_xy)))
            else:
                log("【替换】%s: 反推锚点不行(%s) → 改用图纸定位。" % (old_fname, why))

        # ── ② 兜底: 读图纸按圆锚点吸附 ────────────────────────────────────
        if anchors_xy is None:
            layers_ = _fallback_layers()
            if layers_ is None:
                log("  图纸也不可用, 这条跳过(什么都不动)。")
                st["skip"] += 1
                continue
            dxf_anchors = collect_circle_anchors(layers_, rule, log=log)
            if not dxf_anchors:
                log("  按新规格的定位规则(图层=%s, 半径 %.4g~%.4g)在图纸上没找到"
                    "位置, 跳过。" % (rule["layer"] or "全部",
                                   rule["r_min"], rule["r_max"]))
                st["skip"] += 1
                continue
            pts = [((bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0)
                   for _b, bb in olds]
            picked, unmatched = snap_bodies_to_anchors(dxf_anchors, pts)
            if unmatched:
                log("  警告: %d 个位置对不上图纸锚点(超出容差), 这些件保持原样不动。"
                    % len(unmatched))
            if not picked:
                log("  一个位置都对不上, 整条跳过(什么都不动)。")
                st["skip"] += 1
                continue
            anchors_xy = [(x, y, ang) for x, y, ang, _ix in picked]
            use_idx = [k for _x, _y, _a, idxs in picked for k in idxs]
            st["used_dxf"] += 1
            st["dxf_parts"].append(old_fname)
            log("【替换】★ %s 这条用了图纸定位(图纸=%s)。"
                % (old_fname, os.path.basename(dxf_cache["path"] or "")))

        matched = [olds[k][0] for k in use_idx]
        to_delete.extend(matched)
        to_place[new_fname] = rule
        # 两个旧规格换成同一个新规格时, 锚点要合并而不是覆盖
        anchors_override.setdefault(new_fname, []).extend(anchors_xy)
        st["new"] += len(anchors_xy)
        log("【替换】%s → %s: %d 处(从 %d 个旧件体里归出的实例数)。"
            % (old_fname, new_fname, len(anchors_xy), len(olds)))

    if not to_place:
        log("【替换】没有可替换的对象, 结束(模型一点没动)。")
        return st

    st["pairs"] = len(to_place)
    st["old"] = len({id(b) for b in to_delete})
    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                               "CAD3D 替换标准件")
    try:
        stats = {}
        place_std_parts(session, work_part, dxf_cache["layers"], flb_regions,
                        params, to_place, log, stats=stats,
                        anchors_override=anchors_override)
        # 与主脚本同款收尾: 清掉建模步骤 → 用户要的是实体, 不是提升体
        new_bodies = list((stats.get("STD") or {}).get("bodies") or [])
        _remove_parameters(session, work_part, new_bodies, log)
        _batch_delete(session, to_delete, log, "被换掉的旧标准件")
        _refresh_display(session, work_part, log)
        st["ok"] = True
    except Exception as ex:
        log("【错误】%s" % ex)
        try:
            session.UndoToMark(mark, "CAD3D 替换出错回滚")
            log("【回滚】已撤销本次全部改动。")
        except Exception as ex2:
            log("【回滚失败】%s" % ex2)
    return st


def replace_std_parts(dxf, params, jrt, rules, session, std_rules_all=None,
                      selected=None, ui=None, jt_link_mode=None, mapping=None,
                      state=None):
    """第三页 OK/Apply 的执行回调(签名兼容 execute_pipeline, 供界面注入)。

    只用到 params / rules / mapping: jrt、std_rules_all、selected、
    jt_link_mode 是界面按主脚本惯例传下来的上下文, 本脚本不用。
    dxf 一般是 None —— 图纸只在"反推锚点失败"时才懒加载。
    """
    import NXOpen

    work_part = session.Parts.Work
    if work_part is None:
        if ui is not None:
            ui.NXMessageBox.Show("CAD3D 替换标准件",
                                 NXOpen.NXMessageBox.DialogType.Warning,
                                 "没有工作部件, 没法替换。")
        return False
    log = Log(session)
    log("")
    log("================ NX 一键替换标准件 v%s ================" % SCRIPT_VERSION)
    log("【输入】工作部件: %s" % work_part.Name)
    if not mapping:
        log("【替换】没有指定任何替换关系, 什么都不做。")
        _save_report("std_replace_report.txt", log.lines)
        print("REPLACE RESULT ok=False reason=empty_map")
        return False

    holder = {"path": dxf if (dxf and os.path.isfile(dxf)) else None}

    def _get_dxf():
        if holder["path"] is None:
            holder["path"] = _resolve_dxf(state if state is not None
                                          else load_state(), log, ui)
        return holder["path"]

    st = _do_replace(session, work_part, mapping, rules or {},
                     params or default_params(), log, dxf_getter=_get_dxf)
    if st["used_dxf"]:
        log("【图纸】本次有 %d 条件走了图纸兜底: %s"
            % (st["used_dxf"], ", ".join(st["dxf_parts"])))
        log("        （反推锚点没成功才会走到这里 —— 把这条记下来，"
            "如果一直用不上图纸，图纸逻辑就可以撤掉了。）")
    else:
        log("【图纸】本次全程没用图纸, 全靠反推锚点定位。")
    log("【完成】换掉旧件 %d 个, 放上新件 %d 个, 跳过 %d 条。"
        % (st["old"], st["new"], st["skip"]))
    _save_report("std_replace_report.txt", log.lines)
    try:
        # 只回写"映射"这一项, 不动主脚本的图纸/参数记忆
        save_replace_map(mapping)
    except Exception as ex:
        log("【记忆】映射保存失败(不影响本次结果): %s" % ex)
    if st["used_dxf"] and ui is not None:
        try:
            ui.NXMessageBox.Show(
                "CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Information,
                "有 %d 件这次用了图纸兜底定位（反推锚点没成功）：\n%s\n\n"
                "详细原因见 logs\\std_replace_report.txt。"
                % (st["used_dxf"], "、".join(st["dxf_parts"])))
        except Exception:
            pass
    print("REPLACE RESULT ok=%s pairs=%d old=%d new=%d skip=%d used_dxf=%d"
          % (st["ok"], st["pairs"], st["old"], st["new"], st["skip"],
             st["used_dxf"]))
    return bool(st["ok"])


def _pick_replace_map(work_part, rules_all, state, ui):
    """第一页: 让用户指定"把哪些换成哪些" → {旧件: 新规格}; None = 取消。"""
    import NXOpen

    rows = scan_model_bodies(work_part, None)
    existing, _n_nopos = _scan_existing_std(rows)
    if not existing:
        ui.NXMessageBox.Show(
            "CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Warning,
            "这个部件里没找到主脚本放的标准件。\n"
            "请先跑一次主脚本（nx_extrude_runner.py）把件放好，再来替换。")
        return None
    old_files = sorted(existing)
    saved_map = state.get("std_replace_map")
    if not isinstance(saved_map, dict):
        saved_map = {}
    map_dlx = write_replace_map_dlx(old_files, sorted(rules_all), saved_map)
    if not map_dlx or not os.path.isfile(map_dlx):
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "替换关系窗口生成失败。")
        return None
    dlg = None
    try:
        dlg = ReplaceMapDialog(map_dlx, old_files, sorted(rules_all))
        return dlg.Launch()
    except Exception as ex:
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "替换关系对话框启动失败: %s" % ex)
        return None
    finally:
        if dlg is not None:
            dlg.Dispose()


def main():
    """两页向导: 指定替换关系 → 逐件微调 → 反推锚点原位替换。"""
    import NXOpen

    print("【本脚本】把模型里已放好的标准件换成你指定的另一个规格，没指定的不动。")
    session = NXOpen.Session.GetSession()
    ui = NXOpen.UI.GetUI()
    if session.Parts.Work is None:
        ui.NXMessageBox.Show("CAD3D 替换标准件",
                             NXOpen.NXMessageBox.DialogType.Warning,
                             "请先打开要替换标准件的部件。")
        return
    work_part = session.Parts.Work

    # 读记忆: 图纸路径 / 每件参数 / 上次的映射(全是只读)
    state = load_state()
    rules_all = merge_std_rules(state)
    if not rules_all:
        ui.NXMessageBox.Show("CAD3D 替换标准件",
                             NXOpen.NXMessageBox.DialogType.Warning,
                             "stdparts 目录里没找到标准件 .prt 文件。")
        return

    # ─── 第一页: 指定"把哪些换成哪些"(上次的映射自动回填) ──────────────────
    mapping = _pick_replace_map(work_part, rules_all, state, ui)
    if mapping is None:
        return                          # 取消 → 整个流程中止
    if not mapping:
        print("没指定任何替换关系, 结束(模型一点没动)。")
        return

    # ─── 第三页: 逐件微调(参数读记忆) → Apply/OK 执行替换 ──────────────────
    rows = scan_model_bodies(work_part, None)
    params0 = _measured_params(rows)
    rules = {f: rules_all[f] for f in sorted(set(mapping.values()))
             if f in rules_all}
    if not rules:
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "要换成的规格在 stdparts 里找不到, 中止。")
        return
    sdx = write_std_dlx(rules, params0)
    if not sdx:
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "标准件参数 .dlx 生成失败。")
        return
    sdlg = None
    try:
        sdlg = StdParamsDialog(sdx, rules, params0, None, None, sorted(rules),
                               std_rules_all=rules_all, jt_mode=None,
                               execute_fn=functools.partial(
                                   replace_std_parts, mapping=mapping,
                                   state=state))
        sdlg.Launch()
    except Exception as ex:
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "标准件参数对话框启动失败: %s" % ex)
    finally:
        if sdlg is not None:
            sdlg.Dispose()


if __name__ == "__main__":
    main()
