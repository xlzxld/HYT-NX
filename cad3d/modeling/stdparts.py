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
    _iter, _bodies_of, _matrix3x3, _mark_type, _type_of, ANCHOR_ATTR, MARK_ATTR
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


def scan_model_bodies(work_part, log=None):
    """扫一遍当前部件, 按体上的类型标记归类 → [(标记, 体, 包围盒), ...]。

    标记由主流水线经 _mark_type 打在体上: 各建模层 = 层代码(FLB/CX/JT/JRT/...),
    标准件 = "STD:<prt 文件名>"。包围盒是 UF 的精确轴对齐盒
    (xmin, ymin, zmin, xmax, ymax, zmax), 取不到时为 None。
    没有标记的体(用户自己画的、旧版流水线产物)不进结果 —— 一键替换只动脚本
    自己放的东西, 不碰用户图形。

    替换流程(2026-09-18 新增)靠它拿到: 旧标准件有哪些(按文件名)与各自位置、
    FLB 体的位置(布尔目标)、各层实测 Z(换规格后重新定位用)。
    """
    rows = []
    if work_part is None:
        return rows
    uf = None
    bbox_fn = None
    try:
        import NXOpen.UF
        uf = NXOpen.UF.UFSession.GetUFSession()
        from cad3d.modeling.mold_cut import _body_bbox
        bbox_fn = _body_bbox
    except Exception as ex:
        if log is not None:
            log("  扫描: 体的位置取不到(离线自测或本 NX 无此接口): %s" % ex)
    for b in _iter(getattr(work_part, "Bodies", None)):
        t = _type_of(b)
        if not t:
            continue                        # 无标记 = 不是脚本放的, 不碰
        bb = bbox_fn(uf, b, log) if bbox_fn is not None else None
        if bb is not None and len(bb) < 6:
            bb = None
        rows.append((t, b, bb))
    if log is not None:
        n_std = sum(1 for t, _b, _bb in rows if t.startswith("STD:"))
        log("  扫描: 脚本产物 %d 个体(其中标准件 %d 个)。" % (len(rows), n_std))
    return rows


def _mark_anchor(obj, anchor, ang, uf):
    """把「记时锚点 + 记时体中心 + 放置角」(7 个数)记在体上。

    反推口径(v3.5, 用户 2026-09-19 定案): **锚点 = 当前体中心 +
    (记时锚点 − 记时体中心)** —— 记时锚点与记时体中心一起构成一个
    **偏移**, 件被平移(挪到模具上)后反推出的锚点会**跟着走**;
    而锚点是在 placed_hook(移面/回位)**之后**记的, 所以长度怎么改
    都不会漂(记时中心就是改完后的中心, 偏移当场就是准的)。
    旧版只存偏移(4 个数)也按同口径换算(老模型兼容)。
    """
    from cad3d.modeling.mold_cut import _body_bbox
    bb = _body_bbox(uf, obj, None) if uf is not None else None
    if not bb or len(bb) < 6:
        return False
    try:
        val = "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f" % (
            float(anchor[0]), float(anchor[1]), float(anchor[2]),
            (float(bb[0]) + float(bb[3])) / 2.0,
            (float(bb[1]) + float(bb[4])) / 2.0,
            (float(bb[2]) + float(bb[5])) / 2.0,
            float(ang or 0.0))
        obj.SetAttribute(ANCHOR_ATTR, val)
        return True
    except Exception:
        return False


def parse_anchor_off(text):
    """(纯逻辑) 读体上的锚点记录 → (记时锚点3, 记时体中心3 或 None, 角度); 坏了/空 → None。

    v3.3 起是 **7 个数**「锚点x, y, z, 记时体中心x, y, z, 角度」——
    记时锚点与记时体中心一起构成偏移(见 _anchor_of_record)。
    旧版是 4 个数「dx, dy, dz, 角度」= 锚点 − 体中心 的偏移(老模型兼容)。
    """
    try:
        parts = [float(v) for v in str(text).split(",")]
    except (TypeError, ValueError):
        return None
    if len(parts) >= 7:
        return ((parts[0], parts[1], parts[2]),
                (parts[3], parts[4], parts[5]), parts[6])
    if len(parts) >= 3:
        return ((parts[0], parts[1], parts[2]), None,
                parts[3] if len(parts) > 3 else 0.0)
    return None


def _anchor_of_record(bb, rec):
    """(纯逻辑) 体记录 + 当前包围盒 → 该体的锚点 (x, y, z, 角度)。

    动态锚点(v3.5, 用户 2026-09-19 定案): **锚点 = 当前体中心 + 记时偏移**,
    记时偏移 = 记时锚点 − 记时体中心(7 数记录); 件被平移(挪到模具上)后,
    当前体中心跟着走 → 反推出的锚点**跟着走**。
    旧格式(4 数, 只存偏移)同口径: 锚点 = 当前体中心 + 偏移。
    ⚠️ 只跟平移; 旋转对位不在支持范围(记录里没有角度信息可用)。
    """
    anch, ctr, ang = rec
    cx = (float(bb[0]) + float(bb[3])) / 2.0
    cy = (float(bb[1]) + float(bb[4])) / 2.0
    cz = (float(bb[2]) + float(bb[5])) / 2.0
    if ctr is not None:
        ox = float(anch[0]) - float(ctr[0])
        oy = float(anch[1]) - float(ctr[1])
        oz = float(anch[2]) - float(ctr[2])
    else:
        ox, oy, oz = float(anch[0]), float(anch[1]), float(anch[2])
    return (cx + ox, cy + oy, cz + oz, float(ang or 0.0))


def anchors_from_offsets(items, tol=0.05):
    """(纯逻辑) 体上的锚点记录 → 去重后的实例锚点 + 缺记录的体数。

    items: [(包围盒6, 解析后的记录 或 None), ...] —— 每个体一条。
    同件的多个体各算一次, 算出来**必须重合**(纯算术), 所以按重合去重即得
    "一个实例一个锚点" —— 不用认实体、不用图纸、也不会留下没处理的体。
    返回 ([(x, y, z, ang), ...], 缺记录的体数)
    """
    out = []
    missing = 0
    for row in (items or []):
        try:
            bb, rec = row
            if rec is None or len(bb) < 6:
                missing += 1
                continue
            a = _anchor_of_record(bb, rec)
        except (TypeError, ValueError, IndexError):
            missing += 1
            continue
        for e in out:
            if (abs(a[0] - e[0]) <= tol and abs(a[1] - e[1]) <= tol
                    and abs(a[2] - e[2]) <= tol):
                break
        else:
            out.append(a)
    return out, missing


def group_anchor_instances(items, tol=0.05):
    """(纯逻辑) [(包围盒6, 解析后的记录|None)] → [((x,y,z,ang), [体下标...]), ...]。

    与 anchors_from_offsets 同一"锚点重合即同实例"口径, 但保留分组信息
    (哪些体属于哪一处实例) —— 热咀替换调长度要按实例算旧件长度用。
    没记录/坏记录的体不进任何组。
    """
    groups = []
    for k, row in enumerate(items or []):
        try:
            bb, rec = row
            if rec is None or len(bb) < 6:
                continue
            a = _anchor_of_record(bb, rec)
        except (TypeError, ValueError, IndexError):
            continue
        for g in groups:
            if (abs(a[0] - g[0][0]) <= tol and abs(a[1] - g[0][1]) <= tol
                    and abs(a[2] - g[0][2]) <= tol):
                g[1].append(k)
                break
        else:
            groups.append((a, [k]))
    return groups


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
                    stats=None, anchors_override=None, placed_hook=None):
    """阶段 6: 按规则放置 stdparts 标准件(独立体)并按需布尔。

    anchors_override: {prt 文件名: [(x, y, z[, 角度]), ...]} —— 一键替换标准件时直接
      指定放置点(取自被换掉的旧件体上记的锚点), 不去图纸找圆, z 也照给的走
      (件被挪过 Z 也能跟上); 传 None 走原逻辑(按 DXF 圆锚点), 主流水线行为不变。
    placed_hook: 可选钩子 (fname, 序号(1起), 锚点, 规则, 体列表, 待删组件列表)
      → 新体列表 —— 每处实例放好并提升后、**打类型标记与记锚点之前**调用
      (钩子可能改几何, 锚点必须按改完后的体中心记, 否则记下的偏移当场过期);
      返回的列表替换原体列表(热咀替换调长度用: 就地移面对齐旧件长度, 体列表
      原样返回)。主流水线不传(默认 None), 行为零变化。

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
    uf = None
    try:
        import NXOpen.UF
        uf = NXOpen.UF.UFSession.GetUFSession()
    except Exception as ex:
        log("【标准件】拿不到 UF 会话, 体上不记锚点(%s)—— 以后替换这些件会报"
            "“无标准件锚点”。" % ex)
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
        if anchors_override is not None:
            # 替换模式: 放置点由调用方给定(取自被换掉的旧件体上记的锚点),
            # 不去图纸找圆; z 也照给的走(件被挪过 Z 也能跟上)
            anchors = []
            for _a in (anchors_override.get(fname) or []):
                try:
                    anchors.append((float(_a[0]), float(_a[1]),
                                    float(_a[2]) if len(_a) > 2 else None,
                                    float(_a[3]) if len(_a) > 3 else 0.0))
                except (TypeError, ValueError, IndexError) as ex:
                    log("【标准件】%s: 有个替换位置读不出来, 已跳过(%s)。" % (fname, ex))
        else:
            anchors = [(a[0], a[1], None, float(a[2]) if len(a) > 2 else 0.0)
                       for a in collect_circle_anchors(layers, rule, log=log)]
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
            z_i = z if anch[2] is None else float(anch[2])
            ang = float(anch[3]) if auto_rot else 0.0
            m3 = _matrix3x3(nx, flip, ang)
            name = "%s%s_%d" % (COMP_PREFIX, stem, i + 1)
            try:
                dx, dy, dz = _place_delta((ref_xy[0], ref_xy[1], ref_z),
                                          flip, off)
                dx, dy = _rot_xy(dx, dy, ang)
                pos = nx.Point3d(cx + dx, cy + dy, z_i + dz)
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
            if placed_hook is not None:
                # ⚠️ 顺序不能反(2026-09-18 修): 钩子会**改几何**(热咀替换调长度 =
                # 就地移面), 而锚点记的是「锚点 − 该体包围盒**中心**」—— 必须在
                # 几何定下来之后才记。若先记后移面, 记下的偏移当场就过期, 下次
                # 替换按「当前体中心 + 偏移」反推出来的锚点就偏了(体中心变了、
                # 偏移没跟着变), 同件的多个体还会因此算出不重合的锚点、归组散架
                # → 表现为"多替换几次后 Z 轴越换越偏、旧件长度也量得忽长忽短"。
                _adj = placed_hook(fname, i + 1, anch, rule, tools_all,
                                   pending_comps)
                if _adj:
                    tools_all = _adj
            # 锚点记录(一键替换用): 记放置位置(= 锚点, 无预偏移)
            for _tb in tools_all:                   # 体类型标记(模具开框规则用)
                _mark_type(_tb, "STD:" + fname)
                _mark_anchor(_tb, (cx, cy, z_i), ang, uf)
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
