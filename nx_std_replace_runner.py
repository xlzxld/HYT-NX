# -*- coding: utf-8 -*-
"""
nx_std_replace_runner.py —— 一键替换标准件（你指定换哪个）NX 日记入口 (v3.2)
=============================================================================
适用环境：Siemens NX 10 / NX 12 / NX 2312 及以上版本
播放方式：NX 菜单 工具 → 日记 → 播放，选本文件。
【本脚本】把模型里已放好的标准件换成你指定的另一个规格，没指定的不动。

【前提】已用 nx_extrude_runner.py 跑完分层拉伸并放好标准件。
  ⚠️ 必须是**新版主脚本**建的模型 —— 它会把每个标准件体的锚点记在体上
     （属性 CAD3D_ANCHOR_OFF）。老模型没有这条记录，脚本会直接报
     “无标准件锚点”并原样不动；请先重跑一次主脚本再替换。

【第一页 = 指定替换关系】左边列出模型里当前实际存在的标准件（靠体上的
  CAD3D_TYPE 标记认，没有标记的东西一律不碰），右边挑要换成哪个规格；
  留在“不替换”上的整件保持原样。**不记上次选过什么**，每次都从“不替换”
  开始现选（v3.1 定案：两页都不要记忆）。

【位置怎么定 —— 读体上记的锚点，全程不读图纸】
  主脚本放置时把「锚点 − 该体包围盒中心」和放置角记在**每个体**上。替换时：
      当前锚点 = 当前体中心 + 偏移
  记的是偏移不是绝对坐标 ⇒ 你手动把标准件挪到别处，反推出来的锚点会
  **跟着走**（动态锚点）。同一个件的多个体各算一次必须重合：这既是归组的
  依据（一个实例只放一个新件，治“重复替换好几个”），也是正确性自检。
  好处：不用认“哪个实体带锚点”、不用比尺寸、不用图纸，也不会再出现
  “对不上就留下没删”的遗留。

【热咀长度自动对齐（v3.2 起用"移动面"）】换热咀族(大水口/点胶口/热咀/nozzle,
  关键词可配)时，新件放好后自动按**旧件的顶部到底部长度**调整新件长度：头部
  (顶部往下 30mm 这一段)不动，**这一带以下的面就地移面** —— 比旧件短就拉长、
  比旧件长就缩短。用同步建模「移动面」就地改面(体不重建、头身不留缝)，与手动
  "移动面"选面做法同口径。族关键词与保留高度在 nx_std_config.py 的
  NOZZLE_FAMILIES / NOZZLE_KEEP_HEAD 配置。

【长度是怎么量的】旧件长度 = 该处实例**所有体**的世界 Z 最高减最低（包围盒
  口径，不是件的名义高度）；新件同理。日志里会逐实例打出"几个体、Z 从哪到哪
  → 长多少"，量得对不对可以直接对着看。

【第二页 = 逐件微调】要换成的规格逐件调参数。**参数也不读记忆**，每次都从
  nx_std_config.py 出厂默认开始（Z 基准值按模型实测高度显示）。

【产出】换完的件与主脚本产物同款：普通实体（已清掉建模步骤，不是提升体）。
【记忆】什么都不记（v3.1）：映射和参数每次都从出厂默认开始，也不回写。
【产出判读】控制台最后一行 + logs/std_replace_report.txt:
  REPLACE RESULT ok=True pairs=N old=X new=Y skip=S adj=A
  (adj = 热咀长度对齐成功的处数)
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

from cad3d.core.constants import SCRIPT_VERSION, TARGET_CODE
from cad3d.core.guide import print_guide
from cad3d.core.logging import Log
from cad3d.core.paths import _logs_dir
from cad3d.core.state import default_params, load_state
from cad3d.modeling.display import _refresh_display
from cad3d.modeling.nozzle_len import is_nozzle, make_nozzle_hook
from cad3d.modeling.nx_compat import _anchor_of
from cad3d.modeling.std_rules import (
    _rule_usable,
    guess_std_rule,
    merge_std_rules,
    sanitize_std_rule,
)
from cad3d.modeling.stdparts import (
    _batch_delete,
    _remove_parameters,
    anchors_from_offsets,
    group_anchor_instances,
    parse_anchor_off,
    place_std_parts,
    scan_model_bodies,
)
from cad3d.ui.dialogs import ReplaceMapDialog, StdParamsDialog
from cad3d.ui.dlx_builder import write_replace_map_dlx, write_std_dlx

# 没有锚点记录时的统一说法(用户定案 2026-09-18)
_NO_ANCHOR = "无标准件锚点"


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


def _derive_anchors(old_fname, olds, log):
    """读体上记的锚点 → 这个旧件的实例放置点列表。

    返回 (锚点4元组列表, 参与替换的体下标列表, 失败原因);
    成功时原因为空串, 失败(全部体都没记录)时锚点列表为 None。
    """
    items = [(bb, parse_anchor_off(_anchor_of(b))) for b, bb in olds]
    anchors, missing = anchors_from_offsets(items)
    if not anchors:
        return None, [], _NO_ANCHOR
    if missing:
        log("【替换】%s: 有 %d 个体没有锚点记录(%s), 这些体保持原样不动。"
            % (old_fname, missing, _NO_ANCHOR))
    use_idx = [k for k, (_bb, off) in enumerate(items) if off is not None]
    return anchors, use_idx, ""


def _old_instance_lens(olds, spans=None):
    """(纯逻辑) 旧件体按锚点归实例 → [(实例锚点, 实例长度, 明细), ...]。

    实例长度 = 该实例**全部体**的"顶到底" —— 热咀替换调长度就按这个对齐。
    **口径与新件完全一致**(用户 2026-09-18 定案): 顶取朝上的平面里最高的、底取
    朝下的平面里最低的, 顶上的小凸起不算(见 nozzle_len.plane_span)。

    spans: [(top, bot) 或 None, ...] 与 olds 等长 —— 按上面那个口径量出来的每体
      顶/底(由 `_body_spans` 在 NX 里读); 给 None 的体退回自己的包围盒。
    明细("几个体, Z 从哪到哪")是给人核对的诊断串, 替换日志会逐条打出来。
    没记录/坏记录的体不参与(与替换同口径)。
    """
    items = [(bb, parse_anchor_off(_anchor_of(b))) for b, bb in olds]
    out = []
    for anch, idxs in group_anchor_instances(items):
        zs = []
        for k in idxs:
            sp = spans[k] if (spans and k < len(spans)) else None
            if sp and sp[0] is not None and sp[1] is not None:
                zs.append((float(sp[0]), float(sp[1])))
            elif olds[k][1] and len(olds[k][1]) >= 6:
                zs.append((float(olds[k][1][5]), float(olds[k][1][2])))
        if not zs:
            continue
        z_hi = max(z[0] for z in zs)
        z_lo = min(z[1] for z in zs)
        out.append((anch, z_hi - z_lo,
                    "%d 个体, Z %.4g~%.4g" % (len(zs), z_lo, z_hi)))
    return out


def _body_spans(bodies):
    """(NX 薄壳) 一组体 → [(top, bot) 或 None, ...] —— 按"主平面口径"量顶/底。

    与 nozzle_len.plane_span 同一口径: **旧件长度必须和新件用一样的量法**, 否则
    两边口径不同、白对齐。读不到的体回 None(调用方退回包围盒)。
    """
    from cad3d.modeling.nozzle_len import plane_span, read_face_rows
    out = []
    try:
        import NXOpen.UF
        uf = NXOpen.UF.UFSession.GetUFSession()
    except Exception:
        return [None] * len(bodies or [])
    from cad3d.modeling.mold_cut import _body_bbox
    for b in (bodies or []):
        try:
            bb = _body_bbox(uf, b, None)
            t, bo, _how = plane_span(read_face_rows(uf, [b]), bb)
            out.append((t, bo) if (t is not None and bo is not None) else None)
        except Exception:
            out.append(None)
    return out


def _measured_params(rows, log=None):
    """出厂默认参数 + 模型实测 Z 范围覆盖(给第三页显示 Z 基准用)。

    替换时的锚点自带 Z(取自旧件记录), 所以这里只影响界面显示;
    实测口径与主流水线一致: 拉伸体的 Z 起止就是 params 的起止, 大值=顶面。
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


def _do_replace(session, work_part, mapping, rules, params, log):
    """核心: 按用户指定的映射把旧规格换成新规格。返回结果字典(不抛异常)。

    只处理 mapping 里点名的旧件; 没点名的标准件一个都不动。
    定位全靠体上记的锚点, 不读图纸。
    """
    import NXOpen

    st = {"ok": False, "pairs": 0, "old": 0, "new": 0, "skip": 0,
          "no_anchor": 0, "adj": 0, "adj_skip": 0}
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

    to_place, anchors_override, to_delete, old_lens = {}, {}, [], []
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
        anchors, use_idx, why = _derive_anchors(old_fname, olds, log)
        if anchors is None:
            log("【替换】%s → %s: %s, 跳过 —— 模型一点没动; "
                "老模型请先重跑一次主脚本。" % (old_fname, new_fname, why))
            st["skip"] += 1
            st["no_anchor"] += 1
            continue
        matched = [olds[k][0] for k in use_idx]
        to_delete.extend(matched)
        to_place[new_fname] = rule
        # 两个旧规格换成同一个新规格时, 锚点要合并而不是覆盖
        anchors_override.setdefault(new_fname, []).extend(anchors)
        if is_nozzle(new_fname):
            # 热咀: 按旧件实例长度对齐新件长度(头部不动, 其余就地移面)
            # 长度按"主平面口径"量旧件 —— 和新件同一口径, 见 _body_spans
            lens = _old_instance_lens(olds, _body_spans([b for b, _bb in olds]))
            old_lens.extend((a, L) for a, L, _d in lens)
            # 逐实例打明细: 长度是"该实例所有体的世界 Z 最高减最低", 打出体数与
            # Z 范围, 量得准不准一眼能对上; 锚点坐标也打出来 —— 它就是主脚本
            # 放置时记下的那个定位点(图纸圆心), 拿它跟模型里的实际位置对一下就
            # 知道锚点有没有漂(用户 2026-09-18 反馈"Z 轴偏移"要的就是这个证据)
            for _k, (_a, _L, _d) in enumerate(lens, 1):
                log("【替换】  旧件实例 %d: %s → 长 %.4g; 锚点 (%.3f, %.3f, %.3f)"
                    % (_k, _d, _L, _a[0], _a[1], _a[2]))
            if lens:
                log("【替换】%s → %s: %d 处(从 %d 个旧件体里归出的实例数), "
                    "位置取自体上记的锚点; 这是热咀, 放好后按旧件长度对齐。"
                    % (old_fname, new_fname, len(anchors), len(olds)))
            else:
                log("【替换】%s → %s: %d 处, 位置取自体上记的锚点; 这是热咀, "
                    "但旧件长度没量到, 这几处不做长度对齐。"
                    % (old_fname, new_fname, len(anchors)))
        else:
            log("【替换】%s → %s: %d 处(从 %d 个旧件体里归出的实例数), "
                "位置取自体上记的锚点。"
                % (old_fname, new_fname, len(anchors), len(olds)))
        st["new"] += len(anchors)

    if not to_place:
        log("【替换】没有可替换的对象, 结束(模型一点没动)。")
        return st

    st["pairs"] = len(to_place)
    st["old"] = len({id(b) for b in to_delete})
    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                               "CAD3D 替换标准件")
    try:
        stats = {}
        adj_stats = {}
        placed_hook = None
        if old_lens:
            placed_hook = make_nozzle_hook(session, work_part, old_lens, log,
                                           adj_stats)
        place_std_parts(session, work_part, None, flb_regions, params,
                        to_place, log, stats=stats,
                        anchors_override=anchors_override,
                        placed_hook=placed_hook)
        st["adj"] = adj_stats.get("adj", 0)
        st["adj_skip"] = adj_stats.get("skip", 0)
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
                      selected=None, ui=None, jt_link_mode=None, mapping=None):
    """第三页 OK/Apply 的执行回调(签名兼容 execute_pipeline, 供界面注入)。

    只用到 params / rules / mapping: dxf、jrt、std_rules_all、selected、
    jt_link_mode 是界面按主脚本惯例传下来的上下文, 本脚本不用(全程不读图纸)。
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
    st = _do_replace(session, work_part, mapping, rules or {},
                     params or default_params(), log)
    log("【完成】换掉旧件 %d 个, 放上新件 %d 个, 跳过 %d 条%s; "
        "热咀长度对齐 %d 处(没对齐 %d 处)。"
        % (st["old"], st["new"], st["skip"],
           ("(其中 %d 条是%s)" % (st["no_anchor"], _NO_ANCHOR))
           if st["no_anchor"] else "",
           st.get("adj", 0), st.get("adj_skip", 0)))
    _save_report("std_replace_report.txt", log.lines)
    if st["no_anchor"] and ui is not None:
        try:
            ui.NXMessageBox.Show(
                "CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Information,
                "有 %d 件是%s，没动它们。\n\n"
                "这些体上没有主脚本记下的锚点；老模型请先重跑一次主脚本"
                "（nx_extrude_runner.py），它会补上锚点记录。"
                % (st["no_anchor"], _NO_ANCHOR))
        except Exception:
            pass
    print("REPLACE RESULT ok=%s pairs=%d old=%d new=%d skip=%d adj=%d"
          % (st["ok"], st["pairs"], st["old"], st["new"], st["skip"],
             st.get("adj", 0)))
    return bool(st["ok"])


def _pick_replace_map(work_part, rules_all, ui):
    """第一页: 让用户指定"把哪些换成哪些" → {旧件: 新规格}; None = 取消。

    不读上次的映射记忆(v3.1): 每次都从"不替换"开始现选。
    """
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
    map_dlx = write_replace_map_dlx(old_files, sorted(rules_all))
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
    """两页向导: 指定替换关系 → 逐件微调 → 按体上记的锚点原位替换。"""
    import NXOpen

    print_guide("nx_std_replace_runner.py", NXOpen.Session.GetSession(),
                NXOpen.UI.GetUI())
    print("【本脚本】把模型里已放好的标准件换成你指定的另一个规格，没指定的不动。")
    session = NXOpen.Session.GetSession()
    ui = NXOpen.UI.GetUI()
    if session.Parts.Work is None:
        ui.NXMessageBox.Show("CAD3D 替换标准件",
                             NXOpen.NXMessageBox.DialogType.Warning,
                             "请先打开要替换标准件的部件。")
        return
    work_part = session.Parts.Work

    state = load_state()
    rules_all = merge_std_rules(state)
    if not rules_all:
        ui.NXMessageBox.Show("CAD3D 替换标准件",
                             NXOpen.NXMessageBox.DialogType.Warning,
                             "stdparts 目录里没找到标准件 .prt 文件。")
        return

    # ─── 第一页: 指定"把哪些换成哪些"(不读记忆, 每次从"不替换"现选) ──────
    mapping = _pick_replace_map(work_part, rules_all, ui)
    if mapping is None:
        return                          # 取消 → 整个流程中止
    if not mapping:
        print("没指定任何替换关系, 结束(模型一点没动)。")
        return

    # ─── 第二页: 逐件微调(参数不读记忆, 恒出厂默认) → Apply/OK 执行替换 ──
    rows = scan_model_bodies(work_part, None)
    params0 = _measured_params(rows)
    rules = {f: sanitize_std_rule(guess_std_rule(f))
             for f in sorted(set(mapping.values())) if f in rules_all}
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
                               execute_fn=functools.partial(replace_std_parts,
                                                            mapping=mapping))
        sdlg.Launch()
    except Exception as ex:
        ui.NXMessageBox.Show("CAD3D 替换标准件", NXOpen.NXMessageBox.DialogType.Error,
                             "标准件参数对话框启动失败: %s" % ex)
    finally:
        if sdlg is not None:
            sdlg.Dispose()


if __name__ == "__main__":
    main()
