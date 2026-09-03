# -*- coding: utf-8 -*-
"""cad3d.modeling.stdparts —— 标准件实例化装配、提升体与布尔切槽。"""

import os
from cad3d.core.paths import stdparts_dir
from cad3d.core.config import _cfg_num
from cad3d.core.constants import (
    COMP_PREFIX, FEATURE_PREFIX, SCRIPT_VERSION, STD_MAX_ANCHORS
)
from cad3d.modeling.nx_compat import (
    _iter, _bodies_of, _matrix3x3, MARK_ATTR
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
        log("  警告: 锚点(%.3f,%.3f)不落在任何 FLB 体包围盒内, "
            "已兜底取第 1 个 FLB 体——请核对是否切错板。" % (cx, cy))
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


def _bool_feature(work_part, op, target, tools, name, log, retain_tools=False):
    """布尔特征(CreateSubtractFeature/CreateUniteFeature)。

    retain_tools=True 保留工具体(切槽保件, 同期刊 CopyTools)。
    v1.9 逐工具容错: 多工具合并调用失败时逐个重试, 零相交的坏工具记日志
    跳过, 不再毁掉整次布尔(垫片第1实体零相交一案)。
    """
    fn = "CreateUniteFeature" if op == "unite" else "CreateSubtractFeature"
    tools = [t for t in tools if t is not None]
    if not tools:
        return []
    feats = None
    if len(tools) == 1:
        feats = _bool_one(work_part, fn, target, tools[0], retain_tools)
    else:
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
            except Exception:
                feats = None
        except Exception:
            feats = None
    if not feats:
        feats = []
        for t in tools:
            fs = _bool_one(work_part, fn, target, t, retain_tools)
            if fs:
                feats.extend(fs)
            else:
                log("  布尔工具跳过(与目标无交集或失败): %s"
                    % str(getattr(t, "Name", t)))
        if not feats:
            return []
    for i, f in enumerate(feats):
        try:
            f.SetName(name or ("%sBOOL_%d" % (FEATURE_PREFIX, i)))
        except Exception:
            pass
        _CREATED_FEATURES.append(f)
    return feats


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
        log("【移除参数】失败(特征树保留): %s" % ex)
        return 0
    finally:
        if bld is not None:
            try:
                bld.Destroy()
            except Exception:
                pass
    del _CREATED_FEATURES[:]
    log("【移除参数】完成: %d 个实体已去参数化(重跑按标记清理)。" % len(ok_bodies))
    return len(ok_bodies)


def _usable_parts(rules, log):
    """(v1.30) 过滤出已配置参考点的可用规则; 未配置的收集并写日志。"""
    unusable = _unusable_names(rules)
    usable = {f: r for f, r in rules.items() if _rule_usable(r)}
    if unusable:
        log("【标准件】提示: 以下标准件未在 nx_std_config.py 填写参考点"
            "(ref), 本次跳过: " + ", ".join(unusable)
            + "。请实测后在 config 精确文件名行中填写。")
    return usable, unusable


def place_std_parts(session, work_part, layers, flb_regions, params, std_rules, log,
                    stats=None):
    """阶段 6: 按规则放置 stdparts 标准件(独立体)并按需布尔。"""
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
    log("【标准件】开始: %d 个件规则。" % len(std_rules))
    ca = work_part.ComponentAssembly
    for fname in sorted(std_rules):
        rule = std_rules[fname]
        if not _rule_usable(rule):
            no_ref.append(fname)
            continue
        path = os.path.join(stdparts_dir(), fname)
        if not os.path.isfile(path):
            log("【标准件】%s: 文件缺失, 跳过。" % fname)
            continue
        if anchors_overflow([], rule):
            log("【标准件】%s: 规则指纹命中护栏(图层=%s 半径%.4g~%.4g, "
                "空图层+大半径=全图放置会卡死), 跳过。请到标准件参数页"
                "检查/恢复默认。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        anchors = collect_circle_anchors(layers, rule)
        if not anchors:
            log("【标准件】%s: 无匹配锚点(图层=%s 半径%.4g~%.4g), 跳过。"
                % (fname, rule["layer"] or "全部", rule["r_min"], rule["r_max"]))
            continue
        if len(anchors) > STD_MAX_ANCHORS:
            log("【标准件】%s: 锚点 %d 个超过护栏 %d——规则疑似配错, "
                "跳过。请到标准件参数页检查/恢复默认。"
                % (fname, len(anchors), STD_MAX_ANCHORS))
            continue

        flip = (rule["dir"] == "-Z")
        z = _std_z(params, rule)
        stem = os.path.splitext(fname)[0]
        ref = rule.get("ref")
        if not (isinstance(ref, (list, tuple)) and len(ref) >= 3):
            log("【标准件】%s: 参考点 ref 未配置或非法, 跳过该件。" % fname)
            continue
        try:
            ref_xy = (float(ref[0]), float(ref[1]))
            ref_z = float(ref[2])
        except (TypeError, ValueError) as ex:
            log("【标准件】%s: 参考点 ref 格式非法(%s), 跳过该件。" % (fname, ex))
            continue
        off = (float(rule.get("off_x", 0.0)), float(rule.get("off_y", 0.0)),
               float(rule.get("off_z", 0.0)))
        log("【标准件】%s: 参考点=配置值 XY=(%.3f,%.3f) Z=%.3f 偏移=(%.3f,%.3f,%.3f)"
            % (fname, ref_xy[0], ref_xy[1], ref_z, off[0], off[1], off[2]))
        n_ok = n_bool = n_body = 0
        for i, anch in enumerate(anchors):
            cx, cy = anch[0], anch[1]
            m3 = _matrix3x3(nx, flip)
            name = "%s%s_%d" % (COMP_PREFIX, stem, i + 1)
            try:
                dx, dy, dz = _place_delta((ref_xy[0], ref_xy[1], ref_z),
                                          flip, off)
                pos = nx.Point3d(cx + dx, cy + dy, z + dz)
                try:
                    comp, _ls = ca.AddComponent(path, "MODEL", name, pos, m3, -1)
                except TypeError:
                    comp = ca.AddComponent(path, "MODEL", name, pos, m3, -1, False)
                n_ok += 1
            except Exception as ex:
                log("  %s 位置 %d 放置失败: %s" % (fname, i + 1, ex))
                continue

            tools_all = _promote_body(work_part, comp,
                                      "%sBODY_%s_%d" % (FEATURE_PREFIX, stem, i + 1),
                                      log, body_index=None)
            tools_all = [t for t in (tools_all or []) if t is not None]
            n_body += len(tools_all)
            try:
                session.UpdateManager.AddToDeleteList([comp])
                session.UpdateManager.DoUpdate(
                    session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删组件"))
            except Exception as ex:
                log("  %s 位置 %d 组件删除失败(提升体不受影响): %s"
                    % (fname, i + 1, ex))

            bm = rule["bool_mode"]
            if bm in ("SUBTRACT", "PLACE_SUBTRACT", "UNITE") and tools_all:
                target = _pick_target(flb_regions, cx, cy, log=log)
                if target is None:
                    log("  %s 位置 %d: 无 FLB 体可布尔, 独立体保留(按放置处理)。"
                        % (fname, i + 1))
                    std_stats["bodies"].extend(tools_all)
                else:
                    op = "unite" if bm == "UNITE" else "subtract"
                    fs = _bool_feature(work_part, op, target, tools_all,
                                       "%s%s_%s_%d" % (FEATURE_PREFIX,
                                                       "UNI" if op == "unite" else "SUB",
                                                       stem, i + 1), log,
                                       retain_tools=True)
                    if fs:
                        n_bool += 1
                    if bm == "SUBTRACT":
                        if fs:
                            try:
                                session.UpdateManager.AddToDeleteList(tools_all)
                                session.UpdateManager.DoUpdate(
                                    session.SetUndoMark(
                                        nx.Session.MarkVisibility.Invisible,
                                        "CAD3D 删多余体"))
                            except Exception:
                                pass
                        else:
                            log("  %s 位置 %d: 布尔未生效, 独立体保留。"
                                % (fname, i + 1))
                            std_stats["bodies"].extend(tools_all)
                    else:
                        std_stats["bodies"].extend(tools_all)
            elif tools_all:
                std_stats["bodies"].extend(tools_all)
        log("【标准件】%s: 放置 %d 处, 独立体 %d 个%s (Z=%.4g, %s)。"
            % (fname, n_ok, n_body,
               (", 布尔 %d 处" % n_bool) if n_bool else "",
               z, rule["bool_mode"]))
    std_stats["profiles"] = len(std_stats["bodies"])
    if no_ref:
        log("【标准件】提示: %d 件未配置参考点已跳过: %s"
            % (len(no_ref), ", ".join(no_ref)))
    stats["STD"] = std_stats
