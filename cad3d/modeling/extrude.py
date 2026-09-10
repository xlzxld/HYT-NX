# -*- coding: utf-8 -*-
"""cad3d.modeling.extrude —— 截面曲线生成、特征拉伸与图层建模。"""

import math
from cad3d.core.constants import (
    LAYER_TABLE, REF_LAYER_TABLE, FEATURE_PREFIX, CHAIN_TOL,
    MANAGED_MIN, MANAGED_MAX
)
from cad3d.core.config import _cfg_bool
from cad3d.core.logging import _fmt_num
from cad3d.modeling.nx_compat import _mark_curve, _bodies_of, _set_expr
from cad3d.modeling.purge import _CREATED_FEATURES
from cad3d.geom.topo import organize_loops


def create_curves(work_part, layers, layer_map, log):
    """按图层建 NX 曲线(线/弧/圆) — 全部 DXF 图层都导入(建模图层+参考图层)。

    layer_map: {DXF 图层名: NX 图层号}(assign_layers 产物)。
    返回 {code: [曲线对象或 None]} — 列表与 DXF 实体一一对应(失败处为 None),
    保证环链索引不漂移(教训同 v9.1 的 eName 对应关系)。
    """
    import NXOpen as nx

    P3d, V3d = nx.Point3d, nx.Vector3d
    mtx = None
    for _attr in ("Matrices", "PointMatrices"):   # 各版本集合名不同, 兼容取用
        coll = getattr(work_part, _attr, None)
        if coll is not None and hasattr(coll, "CreateMatrix"):
            try:
                mtx = coll.CreateMatrix(nx.NXMatrix3d(
                    1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
            except Exception:
                mtx = None
            break

    def make_arc(cx, cy, r, a0, a1):
        c = P3d(cx, cy, 0.0)
        if mtx is not None:
            return work_part.Curves.CreateArc(c, mtx, r, a0, a1)
        return work_part.Curves.CreateArc(c, V3d(1.0, 0.0, 0.0),
                                          V3d(0.0, 1.0, 0.0), r, a0, a1)

    out = {}
    zh = {r[0]: r[1] for r in LAYER_TABLE}
    zh.update({r[0]: r[1] for r in REF_LAYER_TABLE})
    for code in sorted(layers.keys()):
        num = layer_map.get(code, MANAGED_MAX)
        ents = layers.get(code) or []
        made, fails = [], 0
        for e in ents:
            obj = None
            try:
                if e.kind == "line":
                    obj = work_part.Curves.CreateLine(P3d(e.p1[0], e.p1[1], 0.0),
                                                      P3d(e.p2[0], e.p2[1], 0.0))
                elif e.kind == "arc":
                    obj = make_arc(e.c[0], e.c[1], e.r, e.a0, e.a1)
                else:  # circle → 整圆弧
                    obj = make_arc(e.c[0], e.c[1], e.r, 0.0, 2.0 * math.pi)
                obj.Layer = num
                _mark_curve(obj)
            except Exception as ex:
                fails += 1
                if fails <= 3:
                    log("  %s 曲线创建失败(%s): %s" % (code, e.kind, ex))
            made.append(obj)
        out[code] = made
        n_ok = len(made) - fails
        if n_ok:
            extra = ("(有 %d 条没画出来)" % fails) if fails else ""
            log("【曲线】%s(%s): %d 条 → NX 图层 %d %s"
                % (code, zh.get(code, "参考"), n_ok, num, extra))
    return out


def work_part_rules(work_part, curves):
    """曲线列表 → 选择意图规则(BaseCurveDumb: 不做额外链接推断)。"""
    return work_part.ScRuleFactory.CreateRuleBaseCurveDumb(list(curves))


def _add_to_section_compat(section, rules, help_pt):
    """AddToSection 跨版本编组通道(NX10/11/12 与 2312 的唯一差异点)。"""
    import NXOpen as nx
    try:
        section.AddToSection(rules, None, None, None, help_pt,
                             nx.Section.Mode.Create, False)
        return
    except Exception:
        pass
    null = getattr(nx.NXObject, "Null", None)
    section.AddToSection(rules, null, null, null, help_pt,
                         nx.Section.Mode.Create, False)


def _sc_rule_options(work_part):
    """ScRuleFactory.CreateRuleOptions 仅 NX2312 等新版本有; NX10/12 该属性不存在。"""
    try:
        opts = work_part.ScRuleFactory.CreateRuleOptions()
    except Exception:
        return None
    try:
        opts.SetSelectedFromInactive(False)
    except Exception:
        pass
    return opts


def extrude_curves(work_part, curves, start, end, name, bool_op=None, help_pt=None,
                   offset=None, draft=None):
    """拉伸一组封闭环曲线: start/end 为绝对 Z 距离。

    bool_op: None=普通创建; ("subtract"/"unite", 目标体)=拉伸时布尔。
    offset: (start, end) 单侧壁偏置(如 (0,5)=壁厚5, 同期刊); draft: 拔模角(度)。
    """
    import NXOpen as nx
    import NXOpen.Features
    import NXOpen.GeometricUtilities

    bldr = work_part.Features.CreateExtrudeBuilder(nx.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(CHAIN_TOL, CHAIN_TOL, 0.5)
        try:
            section.SetAllowedEntityTypes(nx.Section.AllowTypes.OnlyCurves)
        except Exception:
            pass
        bldr.Section = section
        bldr.AllowSelfIntersectingSection(True)
        rules = [work_part_rules(work_part, curves)]
        hp = help_pt
        if hp is None:
            try:
                hp = curves[0].StartPoint
            except Exception:
                hp = nx.Point3d(0.0, 0.0, 0.0)
        _add_to_section_compat(section, rules, hp)

        bldr.Limits.StartExtend.Value.RightHandSide = _fmt_num(start)
        bldr.Limits.EndExtend.Value.RightHandSide = _fmt_num(end)
        bldr.DistanceTolerance = CHAIN_TOL
        if offset is not None:
            _set_expr(bldr.Offset.StartOffset, _fmt_num(offset[0]))
            _set_expr(bldr.Offset.EndOffset, _fmt_num(offset[1]))
        if draft is not None:
            _set_expr(bldr.Draft.FrontDraftAngle, _fmt_num(draft))
            _set_expr(bldr.Draft.BackDraftAngle, _fmt_num(draft))
        bldr.Direction = work_part.Directions.CreateDirection(
            nx.Point3d(0.0, 0.0, 0.0), nx.Vector3d(0.0, 0.0, 1.0),
            nx.SmartObject.UpdateOption.DontUpdate)
        try:
            bldr.BodyType = nx.Features.Feature.BodyType.Solid
        except Exception:
            pass

        btype = nx.GeometricUtilities.BooleanOperation.BooleanType
        if bool_op is not None:
            op_name, target = bool_op
            bldr.BooleanOperation.Type = (btype.Subtract if op_name == "subtract"
                                          else btype.Unite)
            bldr.BooleanOperation.SetTargetBodies([target])
        else:
            bldr.BooleanOperation.Type = btype.Create

        feat = bldr.CommitFeature()
        try:
            feat.SetName(name)
        except Exception:
            pass
        _CREATED_FEATURES.append(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def modeling_ents(layers, code):
    """建模用 DXF 实体: CX 并入 CXK 的曲线一起找闭环。"""
    ents = list(layers.get(code) or [])
    if code == "CX" and (layers.get("CXK") or []):
        ents += list(layers["CXK"])
    return ents


def _merge_extrude_enabled():
    """合并拉伸提速开关(nx_std_config.py 的 MERGE_PROFILE_EXTRUDE, 默认开)。"""
    return _cfg_bool("MERGE_PROFILE_EXTRUDE", True)


def _merge_note(used):
    """(纯逻辑) 图层完成日志后缀: 一次拉伸多个轮廓时标注(便于核对提速路径)。"""
    return ", 多个轮廓一次拉伸" if used else ""


def _merge_groups(role, entries):
    """(纯逻辑, 可离线测) 合并拉伸分组。

    entries = [{"pick": FLB 体或 None, ...}, ...](build_layer 预解析产物)。
      role == "subtract": 按布尔目标体分组——同目标的轮廓合并为一个截面
        一次拉伸+一次布尔; 无目标的(不落在 FLB 内)单独成组普通拉伸;
      其余角色: 全部轮廓并成一组(target 角色不跨轮廓合并, 由调用方
        逐轮廓走"含孔单特征"路径, 不经过本函数的组)。
    返回 [(pick, [entry, ...]), ...](保序)。
    """
    if role != "subtract":
        return [(None, list(entries))]
    groups, keys = {}, []
    for en in entries:
        k = id(en["pick"])
        if k not in groups:
            groups[k] = (en["pick"], [])
            keys.append(k)
        groups[k][1].append(en)
    return [groups[k] for k in keys]


def build_layer(session, work_part, code, zh, role, layers, nx_curves_by_ent,
                params, flb_regions, log, stats):
    """单图层建模: 环组织 → 拉伸 → 布尔。

    (v2.4 提速) 默认开启合并拉伸(MERGE_PROFILE_EXTRUDE 可关):
      含孔轮廓: 外环+全部孔环并入同一截面, 单特征成体——嵌套闭环截面
        NX 自动按孔处理, 与旧版"外环拉伸+逐孔布尔"几何等价;
      subtract 层: 同一 FLB 目标的多轮廓合并成一次拉伸+一次布尔
        (减法对工具并集与逐个减等价);
      target 层: 各轮廓独立成体(维持 regions 逐轮廓映射), 仅做含孔合并;
      任一合并拉伸失败自动回退旧版逐轮廓路径, 容错语义不变。
    """
    d = params.get(code, (0.0, 0.0)) if isinstance(params, dict) else (0.0, 0.0)
    if not isinstance(d, (list, tuple)) or len(d) != 2:
        d = (0.0, 0.0)
    try:
        start, end = float(d[0]), float(d[1])
    except (TypeError, ValueError):
        start, end = 0.0, 0.0
    ents = modeling_ents(layers, code)
    ncurves = len(ents)
    stats[code] = {"curves": ncurves, "profiles": 0, "features": 0, "bodies": [],
                   "note": ""}

    if abs(start) < 1e-12 and abs(end) < 1e-12:
        stats[code]["note"] = "距离全 0, 跳过"
        log("【%s】起始=结束=0, 跳过这一层。" % code)
        return [], []
    if start > end:
        start, end = end, start
        stats[code]["note"] = "起始>结束, 已交换"
        log("【%s】起始比结束大, 已自动对调成 %.4g→%.4g。" % (code, start, end))
    if abs(end - start) < 1e-12:
        stats[code]["note"] = "零厚度, 跳过"
        log("【%s】起始和结束一样, 厚度是 0, 没法拉伸, 跳过。" % code)
        return [], []
    if not ents:
        stats[code]["note"] = "该层没有线"
        log("【%s】图纸上没有这一层的线(距离 %.4g→%.4g), 跳过。"
            % (code, start, end))
        return [], []

    profiles, opens, _nc = organize_loops(ents)
    stats[code]["profiles"] = len(profiles)
    if opens:
        log("【%s】提醒: 有 %d 条线两头没接上, 不参与拉伸。" % (code, len(opens)))
    if not profiles:
        stats[code]["note"] = "没有闭合的轮廓"
        log("【%s】没找到闭合的轮廓, 跳过拉伸。" % code)
        return [], []

    def pick_region(bbox):
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        for body, b in flb_regions:
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                return body
        return None

    nx_curves = modeling_ents(nx_curves_by_ent, code)
    bodies, regions = [], []
    fi = 0

    def chain_curves(item):
        if item.get("chain") is not None:
            idxs = [i for (i, _r) in item["chain"]]
        else:
            try:
                idxs = [ents.index(item["circle"])]
            except (ValueError, KeyError):
                return None
        cs = [nx_curves[i] for i in idxs if 0 <= i < len(nx_curves)]
        if len(cs) != len(idxs) or any(c is None for c in cs):
            log("【%s】这个轮廓里有没画出来的线, 跳过。" % code)
            return None
        return cs

    def chain_help(item):
        import NXOpen as nx
        if item.get("chain") is not None:
            e = ents[item["chain"][0][0]]
            p = e.p1 if e.kind != "circle" else (e.c[0] + e.r, e.c[1])
        else:
            c = item["circle"]
            p = (c.c[0] + c.r, c.c[1])
        return nx.Point3d(p[0], p[1], 0.0)

    # 预解析: 逐轮廓收集曲线与布尔目标(失败轮廓照旧日志后跳过)
    entries = []
    for prof in profiles:
        fi += 1
        outer_curves = chain_curves(prof["outer"])
        if outer_curves is None:
            continue
        holes = []
        for k, hole in enumerate(prof["holes"]):
            hc = chain_curves(hole)
            if hc is not None:
                holes.append((k, hole, hc))
        pick = None
        if role == "subtract":
            if flb_regions:
                pick = pick_region(prof["outer"]["bbox"])
                if pick is None:
                    log("【%s】轮廓 %d 不落在任何分流板里, 当普通实体留着。"
                        % (code, fi))
            else:
                log("【%s】没有分流板, 轮廓当普通实体留着。" % code)
        entries.append({"fi": fi,
                        "base": "%sEXT_%s_%d" % (FEATURE_PREFIX, code, fi),
                        "outer": outer_curves, "hp": chain_help(prof["outer"]),
                        "holes": holes, "pick": pick,
                        "bbox": prof["outer"]["bbox"]})

    def _classic(en):
        """旧版逐轮廓路径(合并关闭/合并失败回退共用, 行为与 v2.3 一致)。"""
        op = ("subtract", en["pick"]) if (role == "subtract"
                                          and en["pick"] is not None) else None
        try:
            feat = extrude_curves(work_part, en["outer"], start, end,
                                  en["base"] + ("_OUT" if en["holes"] else ""),
                                  bool_op=op, help_pt=en["hp"])
            stats[code]["features"] += 1
        except Exception as ex:
            stats[code]["note"] = "拉伸失败"
            log("【%s】轮廓 %d 拉伸失败: %s" % (code, en["fi"], ex))
            return
        got = _bodies_of(feat)
        if op is None:
            bodies.extend(got)
        if role == "target" and got:
            regions.append((got[0], en["bbox"]))
        for k, hole, hc in en["holes"]:
            if op is not None:
                hop = ("unite", en["pick"])
                hname = en["base"] + "_CORE%d" % k
            else:
                host = got[0] if got else None
                if host is None:
                    continue
                hop = ("subtract", host)
                hname = en["base"] + "_H%d" % k
            try:
                extrude_curves(work_part, hc, start, end, hname,
                               bool_op=hop, help_pt=chain_help(hole))
                stats[code]["features"] += 1
            except Exception as ex:
                stats[code]["note"] = "孔没挖成"
                log("【%s】轮廓 %d 的第 %d 个孔没挖成: %s"
                    % (code, en["fi"], k, ex))

    def _merged(ens, name, op):
        """提速路径: 多轮廓/含孔截面并入同一 section, 单特征一次成体。"""
        curves = []
        for en in ens:
            curves.extend(en["outer"])
            for _k, _hole, hc in en["holes"]:
                curves.extend(hc)
        feat = extrude_curves(work_part, curves, start, end, name,
                              bool_op=op, help_pt=ens[0]["hp"])
        stats[code]["features"] += 1
        got = _bodies_of(feat)
        if op is None:
            bodies.extend(got)
        if role == "target" and got:
            regions.append((got[0], ens[0]["bbox"]))

    merged_used = False
    if _merge_extrude_enabled() and entries:
        if role == "target":
            # 各轮廓独立成体(regions 逐轮廓映射), 仅做含孔单特征合并
            for en in entries:
                try:
                    _merged([en], en["base"], None)
                    merged_used = True
                except Exception as ex:
                    stats[code]["note"] = "改成逐个拉伸"
                    log("【%s】轮廓 %d 带孔一次拉伸失败(%s), 改成一个个轮廓单独拉。"
                        % (code, en["fi"], ex))
                    _classic(en)
        else:
            for gi, (pick, gents) in enumerate(_merge_groups(role, entries), 1):
                gop = ("subtract", pick) if pick is not None else None
                try:
                    _merged(gents, "%sEXT_%s_M%d" % (FEATURE_PREFIX, code, gi),
                            gop)
                    merged_used = True
                except Exception as ex:
                    stats[code]["note"] = "改成逐个拉伸"
                    log("【%s】第 %d 组(%d 个轮廓)一次拉伸失败(%s), "
                        "改成一个个轮廓单独拉。" % (code, gi, len(gents), ex))
                    for en in gents:
                        _classic(en)
    else:
        for en in entries:
            _classic(en)

    if role == "target":
        log("【%s】这个图层做好了: %d 个轮廓 → %d 个实体, 高度 %.4g→%.4g%s。"
            % (code, len(profiles), len(regions), start, end,
               _merge_note(merged_used)))
    elif role == "subtract":
        log("【%s】挖孔完成: %d 个轮廓从分流板减掉%s。"
            % (code, len(profiles), _merge_note(merged_used)))
    else:
        log("【%s】拉伸完成: %d 个轮廓%s。"
            % (code, len(profiles), _merge_note(merged_used)))
    stats[code]["bodies"] = bodies
    return bodies, regions
