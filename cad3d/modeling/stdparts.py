# -*- coding: utf-8 -*-
"""cad3d.modeling.stdparts —— 标准件实例化装配、提升体与布尔切槽。"""

import math
import os
from cad3d.core.paths import stdparts_dir
from cad3d.core.config import _cfg_num
from cad3d.core.constants import (
    COMP_PREFIX, FEATURE_PREFIX, SCRIPT_VERSION, STD_MAX_ANCHORS
)
from cad3d.modeling.nx_compat import (
    _iter, _bodies_of, _matrix3x3, _mark_type, MARK_ATTR
)
from cad3d.modeling.purge import _CREATED_FEATURES
from cad3d.geom.topo import collect_circle_anchors
from cad3d.modeling.std_rules import (
    _std_z, _rule_usable, _unusable_names, anchors_overflow
)


def _place_delta(ref, flip, off):
    """(纯逻辑)放置位移: basePoint = 锚点 + 本函数返回值。

    basePoint = 锚点 − R·ref + off(R 为插入姿态矩阵):
      +Z(R=I)      → (−ref_x+ox, −ref_y+oy, −ref_z+oz)
      -Z(绕X 180°) → ref 的 y/z 分量随零件坐标系翻转反号——此前直接用
                     −ref, 翻转件对位误差 = (0, 2·ref_y, 2·ref_z)(v1.35 修复)
    """
    ref = ref or (0.0, 0.0, 0.0)
    off = off or (0.0, 0.0, 0.0)
    rx = _cfg_num(ref[0] if len(ref) > 0 else 0.0, 0.0)
    ry = _cfg_num(ref[1] if len(ref) > 1 else 0.0, 0.0)
    rz = _cfg_num(ref[2] if len(ref) > 2 else 0.0, 0.0)
    ox = _cfg_num(off[0] if len(off) > 0 else 0.0, 0.0)
    oy = _cfg_num(off[1] if len(off) > 1 else 0.0, 0.0)
    oz = _cfg_num(off[2] if len(off) > 2 else 0.0, 0.0)
    if flip:
        ry, rz = -ry, -rz
    return (-rx + ox, -ry + oy, -rz + oz)


def _rot_xy(dx, dy, ang_deg):
    """(纯逻辑) 位移向量绕 Z 旋转 ang_deg 度(YXB 逐板自动判向专用)。

    off 在旋转件上按局部系语义随件旋转; ang_deg=0 时恒等(其余件零回归)。"""
    if not ang_deg:
        return dx, dy
    a = math.radians(ang_deg)
    c, s = math.cos(a), math.sin(a)
    return (dx * c - dy * s, dx * s + dy * c)


def _pick_target(flb_regions, cx, cy, log=None):
    """按锚点 XY 找包含它的 FLB 体。

    多个 FLB 体(多通道板)时必须命中包围盒; 一个都命中不了才兜底取第一个
    体——此时切错板的风险很高, 因此兜底一定要在日志里留痕(v1.29: 过去
    是静默兜底, 板外锚点会把孔切到别的板上且无任何提示)。
    """
    for body, b in flb_regions:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return body
    if not flb_regions:
        return None
    if log is not None:
        log("  警告: 放置点(%.3f,%.3f)不落在任何分流板的范围内, 已先按第 1 块"
            "分流板处理——请核对是不是切错板了。" % (cx, cy))
    return flb_regions[0][0]


def _promote_body(work_part, comp, feat_name, log, body_index=None):
    """组件实体 → 提升体(工作部件所有, 可直接作布尔工具)。

    body_index: None=全部实体(返回列表), 0/1=第几个实体(返回单体或 None)。
    v1.8: 逐实体容错——单个实体提升失败(如不在引用集)只跳过并记日志,
    不再让整件失败(主进胶 7 实体一案: 一个坏实体毁掉全部)。
    """
    import NXOpen
    import NXOpen.Features

    proto = comp.Prototype
    bodies = _iter(proto.Bodies)
    if not bodies:
        log("  提升失败: %s 内无实体。" % proto.Name)
        return None
    if body_index is not None:
        if body_index >= len(bodies):
            log("  提升失败: 件内只有 %d 个实体, 无第 %d 个。"
                % (len(bodies), body_index + 1))
            return None
        bodies = [bodies[body_index]]
    out = []
    for bd in bodies:
        try:
            occ = comp.FindOccurrence(bd)
            if occ is None:
                log("  提升跳过一个实体: 不在组件引用集内。")
                continue
            pb = work_part.Features.CreatePromotionBuilder(
                NXOpen.Features.Promotion.Null)
            try:
                pb.Associative = False
                pb.Body.Add(occ)
                feat = pb.CommitFeature()
            finally:
                try:
                    pb.Destroy()
                except Exception:
                    pass
            try:
                feat.SetName(feat_name if len(bodies) == 1
                             else "%s_%d" % (feat_name, len(out) + 1))
            except Exception:
                pass
            _CREATED_FEATURES.append(feat)
            bs = _bodies_of(feat)
            if bs:
                out.append(bs[0])
        except Exception as ex:
            log("  提升实体失败(跳过该实体): %s" % ex)
            continue
    if body_index is not None:
        return out[0] if out else None
    return out


def _bool_one(work_part, fn, target, tool, retain_tools):
    """单工具布尔, 返回特征列表或 None(失败)。"""
    try:
        r = getattr(work_part.Features, fn)(target, False, [tool],
                                            retain_tools, False)
    except TypeError:
        try:
            r = getattr(work_part.Features, fn)(target, False, [tool],
                                                retain_tools, False, False, False)
        except Exception:
            return None
    except Exception:
        return None
    if isinstance(r, tuple):
        r = r[0]
    try:
        return [f for f in r]
    except TypeError:
        return [r]


def _bool_tag(t):
    """体的日志标识: Name 常为空串, 回退 Tag 保证可定位。"""
    return str(getattr(t, "Name", "") or ("Tag=%s" % getattr(t, "Tag", "?")))


def _merge_undo_mark(session):
    """合并减前挂不可见 undo 标记(防 NX 多工具减部分提交); 不可用→None。"""
    if session is None:
        return None
    try:
        import NXOpen
        return session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                   "CAD3D 布尔合并减")
    except ImportError:
        return None            # 非NX环境(离线自测 mock), 无 undo 栈可挂
    except Exception:
        return None            # 建标记失败不阻断减法(与旧版行为一致)


def _merge_undo_rollback(session, mark, log):
    """合并减失败后回滚: NX 多工具减可能已把前面成员减入目标才抛异常,
    不回滚会出现"图上已减、日志报失败"的账实不符(2026-09-08 用户实测)。"""
    if session is None or mark is None:
        return
    try:
        session.UndoToMark(mark, None)
        log("  已回滚合并减的部分效果, 以下逐个减重新对账。")
    except Exception as ex:
        log("  合并减回滚失败(以实际模型为准): %s" % ex)


def _bool_feature(work_part, op, target, tools, name, log, retain_tools=False,
                  with_failed=False, session=None):
    """布尔特征(CreateSubtractFeature/CreateUniteFeature)。

    retain_tools=True 保留工具体(切槽保件, 同期刊 CopyTools)。
    v1.9 逐工具容错: 多工具合并调用失败时逐个重试, 零相交的坏工具记日志
    跳过, 不再毁掉整次布尔(垫片第1实体零相交一案)。
    with_failed=True 返回 (特征列表, 失败工具体列表) 供调用方精确对账
    (模具批量减按失败名单计数); 默认 False 只返回特征列表, 与旧版一致。
    失败工具体在函数内只做一次减法尝试, 不重复调用。
    session 非 None 时(仅 NX 环境): 合并减前挂不可见 undo 标记, 调用失败
    回滚 NX 可能已减入的部分成员后再逐个重减, 保证模型与日志一致。
    """
    fn = "CreateUniteFeature" if op == "unite" else "CreateSubtractFeature"
    tools = [t for t in tools if t is not None]
    if not tools:
        return ([], []) if with_failed else []
    failed = []
    feats = None
    if len(tools) == 1:
        feats = _bool_one(work_part, fn, target, tools[0], retain_tools)
        if not feats:
            failed.append(tools[0])
            log("  布尔工具跳过(与目标无交集或失败): %s"
                % _bool_tag(tools[0]))
    else:
        mk = _merge_undo_mark(session)
        try:
            r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                retain_tools, False)
            if isinstance(r, tuple):
                r = r[0]
            feats = list(r)
        except TypeError:
            try:
                r = getattr(work_part.Features, fn)(target, False, list(tools),
                                                    retain_tools, False, False, False)
                if isinstance(r, tuple):
                    r = r[0]
                feats = list(r)
            except Exception as ex:
                log("  布尔合并调用签名不可用(%s: %s), 逐个减(老版本NX兼容)。"
                    % (type(ex).__name__, ex))
                feats = None
        except Exception as ex:
            log("  布尔合并调用失败(%s: %s), 降级逐个减。"
                % (type(ex).__name__, ex))
            feats = None
        if not feats:
            _merge_undo_rollback(session, mk, log)
            feats = None          # 合并空返回同视作失败, 走逐个定位
        if feats is None:
            for t in tools:
                fs = _bool_one(work_part, fn, target, t, retain_tools)
                if fs:
                    feats = feats or []
                    feats.extend(fs)
                else:
                    failed.append(t)
                    log("  布尔工具跳过(与目标无交集或失败): %s"
                        % _bool_tag(t))
    if feats is None:
        feats = []
    if not feats:
        return ([], failed) if with_failed else []
    for i, f in enumerate(feats):
        try:
            f.SetName(name or ("%sBOOL_%d" % (FEATURE_PREFIX, i)))
        except Exception:
            pass
        _CREATED_FEATURES.append(f)
    return (feats, failed) if with_failed else feats


def _remove_parameters(session, work_part, bodies, log):
    """阶段 8: 移除全部产物参数(用户确认: 执行后只要实体)。

    先给每个体打 MARK_ATTR 标记(与曲线同款), 再 RemoveParameters 去特征树;
    标记是重跑清理的依据(特征没了, nx_purge 按标记识别哑体)。着色在移除
    前完成(颜色保留)。失败记日志保留特征树, 不影响产物。
    """
    ok_bodies = []
    for b in bodies:
        try:
            b.SetAttribute(MARK_ATTR, SCRIPT_VERSION)
            ok_bodies.append(b)
        except Exception:
            pass
    if not ok_bodies:
        return 0
    bld = None
    try:
        bld = work_part.Features.CreateRemoveParametersBuilder()
        for b in ok_bodies:
            try:
                bld.Objects.Add(b)
            except Exception:
                pass
        bld.Commit()
    except Exception as ex:
        log("【移除参数】失败(建模步骤还留着, 不影响实体): %s" % ex)
        return 0
    finally:
        if bld is not None:
            try:
                bld.Destroy()
            except Exception:
                pass
    del _CREATED_FEATURES[:]
    log("【移除参数】完成: %d 个实体已清掉建模步骤(重跑时按标记清理)。"
        % len(ok_bodies))
    return len(ok_bodies)


def _usable_parts(rules, log):
    """(v1.30) 过滤出已配置参考点的可用规则; 未配置的收集并写日志。"""
    unusable = _unusable_names(rules)
    usable = {f: r for f, r in rules.items() if _rule_usable(r)}
    if unusable:
        log("【标准件】提醒: 这些件还没在 nx_std_config.py 里填参考点(ref), "
            "本次跳过: " + ", ".join(unusable)
            + "。请在 config 里给它们各自的精确文件名行补上。")
    return usable, unusable


def _batch_delete(session, objs, log, label):
    """(提速) N 个对象合并为一次全树更新删除, 失败降级逐个删。

    旧版逐锚点删除 = 每锚点一次 DoUpdate(全模型更新, 随特征树增大线性变慢);
    合并后一次更新删完, 删除失败时逐个重试(语义与旧版一致, 仅日志合并)。
    返回实际提交删除的对象数(仅供诊断)。"""
    import NXOpen as nx

    objs = [o for o in objs if o is not None]
    if not objs or session is None:
        return 0
    try:
        session.UpdateManager.AddToDeleteList(list(objs))
        session.UpdateManager.DoUpdate(
            session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                "CAD3D 批量删除" + label))
        return len(objs)
    except Exception as ex:
        log("  批量删除%s失败(%s), 降级逐个删除。" % (label, ex))
    n = 0
    for o in objs:
        try:
            session.UpdateManager.AddToDeleteList([o])
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                    "CAD3D 删除" + label))
            n += 1
        except Exception as ex:
            log("  单个删除%s失败(跳过): %s" % (label, ex))
    return n


def _group_bool_plan(plan):
    """(纯逻辑, 可离线测) 布尔计划按 (目标体, 操作) 保序分组 → 合并执行。

    plan = [(target, op, fname, 序号, bool_mode, tools), ...];
    返回 [(target, op, [(fname, 序号, bool_mode, tools), ...]), ...]。
    同目标的同类操作合并成一次多工具布尔(NX 一次提交一次更新),
    失败仍由 _bool_feature 内部逐工具重试兜底, 几何结果与逐锚点调用等价
    (减法/并法对不相交工具体均满足结合律, 相交工具由 parasolid 内部处理)。
    """
    groups, keys = {}, []
    for target, op, fname, idx, bm, tools in plan:
        k = (id(target), op)
        if k not in groups:
            groups[k] = (target, op, [])
            keys.append(k)
        groups[k][2].append((fname, idx, bm, tools))
    return [groups[k] for k in keys]


def place_std_parts(session, work_part, layers, flb_regions, params, std_rules, log,
                    stats=None):
    """阶段 6: 按规则放置 stdparts 标准件(独立体)并按需布尔。

    (v2.4 提速) 放置与布尔解耦为两段执行, 几何结果与旧版逐锚点完全一致:
      段1 逐锚点: 装配组件 → 提升体(组件不即时删, 只登记待删清单);
      段2 收尾:   ①全部组件一次批量删(1 次全树更新)
                  ②同 (目标体, 操作) 的布尔合并成一次多工具提交
                  ③SUBTRACT 生效工具一次批量删。
    旧版每锚点 2 次显式 DoUpdate + 1 次独立布尔提交, N 锚点 ≈ 3N 次全树
    更新; 现固定 2 次 + 每目标每操作 1 次(提升体为非关联特征, 删除组件
    时机后移不影响其有效性——旧版本就是先删组件再用提升体布尔的)。
    """
    import NXOpen
    import NXOpen as nx
    import NXOpen.Features

    if stats is None:
        stats = {}
    std_stats = {"curves": 0, "profiles": 0, "features": 0,
                 "bodies": [], "note": ""}
    if not std_rules:
        stats["STD"] = std_stats
        return
    no_ref = []
    log("【标准件】开始: 共 %d 个件的规则。" % len(std_rules))
    ca = work_part.ComponentAssembly
    pending_comps = []          # 段2 统一批量删除的临时组件
    bool_plan = []              # 段2 合并执行的布尔计划
    bool_counts = {}            # fname -> 布尔生效锚点数(段2 结算后补日志)
    for fname in sorted(std_rules):
        rule = std_rules[fname]
        if not _rule_usable(rule):
            no_ref.append(fname)
            continue
        path = os.path.join(stdparts_dir(), fname)
        if not os.path.isfile(path):
            log("【标准件】找不到 %s 这个 .prt 文件, 跳过。" % fname)
            continue
        if anchors_overflow([], rule):
            log("【标准件】%s: 规则配得不对(图层=%s, 半径 %.4g~%.4g——没限图层又"
                "放开半径, 会把整张图上的圆都放一遍, 会卡死), 跳过。"
                "请到标准件参数页检查, 或点恢复默认。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        anchors = collect_circle_anchors(layers, rule, log=log)
        if not anchors:
            log("【标准件】%s: 按规则(图层=%s, 半径 %.4g~%.4g)没找到能放的位置, "
                "跳过。" % (fname, rule["layer"] or "全部",
                          rule["r_min"], rule["r_max"]))
            continue
        if len(anchors) > STD_MAX_ANCHORS:
            log("【标准件】%s: 找出来的放置点有 %d 个, 超过上限 %d——规则可能"
                "配错了, 跳过。请到标准件参数页检查, 或点恢复默认。"
                % (fname, len(anchors), STD_MAX_ANCHORS))
            continue

        flip = (rule["dir"] == "-Z")
        z = _std_z(params, rule)
        stem = os.path.splitext(fname)[0]
        ref = rule.get("ref")
        if not (isinstance(ref, (list, tuple)) and len(ref) >= 3):
            log("【标准件】%s: 参考点 ref 没填或格式不对, 这件跳过。" % fname)
            continue
        try:
            ref_xy = (float(ref[0]), float(ref[1]))
            ref_z = float(ref[2])
        except (TypeError, ValueError) as ex:
            log("【标准件】%s: 参考点 ref 格式不对(%s), 这件跳过。" % (fname, ex))
            continue
        off = (float(rule.get("off_x", 0.0)), float(rule.get("off_y", 0.0)),
               float(rule.get("off_z", 0.0)))
        log("【标准件】%s: 用配置的参考点: 原点 XY=(%.3f,%.3f), Z=%.3f, "
            "偏移=(%.3f,%.3f,%.3f)"
            % (fname, ref_xy[0], ref_xy[1], ref_z, off[0], off[1], off[2]))
        auto_rot = (rule["layer"] == "YXB")   # YXB: 贴合边中点锚点+逐板轮廓判向
        if auto_rot:
            log("【标准件】%s: 压线板自动摆方向已启用(16.6 长边贴着槽、落在 "
                "CX 线上, 板体朝背离槽的一侧与 2D 轮廓重合, 每块板的角度照"
                "它自己的轮廓算)。" % fname)
        n_ok = n_body = 0
        for i, anch in enumerate(anchors):
            cx, cy = anch[0], anch[1]
            ang = float(anch[2]) if auto_rot else 0.0
            m3 = _matrix3x3(nx, flip, ang)
            name = "%s%s_%d" % (COMP_PREFIX, stem, i + 1)
            try:
                dx, dy, dz = _place_delta((ref_xy[0], ref_xy[1], ref_z),
                                          flip, off)
                dx, dy = _rot_xy(dx, dy, ang)
                pos = nx.Point3d(cx + dx, cy + dy, z + dz)
                try:
                    comp, _ls = ca.AddComponent(path, "MODEL", name, pos, m3, -1)
                except TypeError:
                    comp = ca.AddComponent(path, "MODEL", name, pos, m3, -1, False)
                n_ok += 1
            except Exception as ex:
                log("  %s 第 %d 处放置失败: %s" % (fname, i + 1, ex))
                continue

            tools_all = _promote_body(work_part, comp,
                                      "%sBODY_%s_%d" % (FEATURE_PREFIX, stem, i + 1),
                                      log, body_index=None)
            tools_all = [t for t in (tools_all or []) if t is not None]
            for _tb in tools_all:                   # 体类型标记(模具开框规则用)
                _mark_type(_tb, "STD:" + fname)
            n_body += len(tools_all)
            pending_comps.append(comp)              # (提速)延到段2 一次删

            bm = rule["bool_mode"]
            if bm in ("SUBTRACT", "PLACE_SUBTRACT", "UNITE") and tools_all:
                target = _pick_target(flb_regions, cx, cy, log=log)
                if target is None:
                    log("  %s 第 %d 处: 不在任何分流板上, 当独立实体留着。"
                        % (fname, i + 1))
                    std_stats["bodies"].extend(tools_all)
                else:
                    op = "unite" if bm == "UNITE" else "subtract"
                    bool_plan.append((target, op, fname, i + 1, bm, tools_all))
            elif tools_all:
                std_stats["bodies"].extend(tools_all)
        log("【标准件】%s: 放了 %d 处, 独立实体 %d 个 (Z=%.4g, 布尔方式 %s)。"
            % (fname, n_ok, n_body, z, rule["bool_mode"]))

    # ── 段2: 统一清理与合并布尔 ────────────────────────────────────────────
    _batch_delete(session, pending_comps, log, "临时组件")
    tools_to_delete = []
    for gi, (target, op, items) in enumerate(_group_bool_plan(bool_plan), 1):
        group_tools = []
        for fname, _idx, _bm, tools in items:
            group_tools.extend(tools)
        _stem = os.path.splitext(items[0][0])[0]
        fs, failed = _bool_feature(work_part, op, target, group_tools,
                                   "%s%s_%s_G%d" % (FEATURE_PREFIX,
                                                    "UNI" if op == "unite" else "SUB",
                                                    _stem, gi),
                                   log, retain_tools=True, with_failed=True,
                                   session=session)
        std_stats["features"] += len(fs or [])
        failed_ids = {id(t) for t in (failed or [])}
        for fname, idx, bm, tools in items:
            ok_any = any(id(t) not in failed_ids for t in tools)
            if ok_any:
                bool_counts[fname] = bool_counts.get(fname, 0) + 1
            if bm == "SUBTRACT":
                if ok_any:
                    # 与旧版一致: 布尔生效即整组工具删除(零相交工具同为废料)
                    tools_to_delete.extend(tools)
                else:
                    log("  %s 第 %d 处: 没挖进去(跟目标没真正相交), 当独立实体留着。"
                        % (fname, idx))
                    std_stats["bodies"].extend(tools)
            else:
                # PLACE_SUBTRACT / UNITE: 工具体保留为独立体(旧版同款)
                std_stats["bodies"].extend(tools)
    _batch_delete(session, tools_to_delete, log, "布尔多余体")
    for fname in sorted(bool_counts):
        log("【标准件】%s: 有 %d 处真挖进去了。" % (fname, bool_counts[fname]))
    std_stats["profiles"] = len(std_stats["bodies"])
    if no_ref:
        log("【标准件】提醒: %d 件没填参考点, 已跳过: %s"
            % (len(no_ref), ", ".join(no_ref)))
    stats["STD"] = std_stats
