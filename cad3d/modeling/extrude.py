# -*- coding: utf-8 -*-
"""cad3d.modeling.extrude —— 截面曲线生成、特征拉伸与图层建模。"""

import math
from cad3d.core.constants import (
    LAYER_TABLE, REF_LAYER_TABLE, FEATURE_PREFIX, CHAIN_TOL,
    MANAGED_MIN, MANAGED_MAX
)
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
            extra = ("(失败 %d)" % fails) if fails else ""
            log("【曲线】%s(%s): %d 条 → NX 图层 %d %s"
                % (code, zh.get(code, "参考"), n_ok, num, extra))
    return out


_create_curves = create_curves


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


def build_layer(session, work_part, code, zh, role, layers, nx_curves_by_ent,
                params, flb_regions, log, stats):
    """单图层建模: 环组织 → 拉伸 → 布尔。"""
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
        log("【%s】起始=结束=0, 跳过该图层。" % code)
        return [], []
    if start > end:
        start, end = end, start
        stats[code]["note"] = "起始>结束, 已交换"
        log("【%s】起始>结束, 已自动交换为 %.4g→%.4g。" % (code, start, end))
    if abs(end - start) < 1e-12:
        stats[code]["note"] = "零厚度, 跳过"
        log("【%s】起始==结束(非零), 零厚度无法拉伸, 跳过。" % code)
        return [], []
    if not ents:
        stats[code]["note"] = "图层无曲线"
        log("【%s】DXF 中无该图层曲线(距离 %.4g→%.4g), 跳过。" % (code, start, end))
        return [], []

    profiles, opens, _nc = organize_loops(ents)
    stats[code]["profiles"] = len(profiles)
    if opens:
        log("【%s】警告: %d 条开口链未闭合, 不参与拉伸。" % (code, len(opens)))
    if not profiles:
        stats[code]["note"] = "无封闭环"
        log("【%s】未找到任何封闭环, 跳过拉伸。" % code)
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
            log("【%s】轮廓含创建失败的曲线, 该轮廓跳过。" % code)
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

    for prof in profiles:
        fi += 1
        base_name = "%sEXT_%s_%d" % (FEATURE_PREFIX, code, fi)
        outer_curves = chain_curves(prof["outer"])
        if outer_curves is None:
            continue
        hp = chain_help(prof["outer"])
        holes = prof["holes"]

        op = None
        pick = None
        if role == "subtract":
            if flb_regions:
                pick = pick_region(prof["outer"]["bbox"])
                if pick is not None:
                    op = ("subtract", pick)
                else:
                    log("【%s】轮廓 %d 不落在任何 FLB 体内, 按普通拉伸保留。"
                        % (code, fi))
            else:
                log("【%s】无 FLB 基准体, 轮廓按普通拉伸保留。" % code)
        try:
            feat = extrude_curves(work_part, outer_curves, start, end,
                                  base_name + ("_OUT" if holes else ""),
                                  bool_op=op, help_pt=hp)
            stats[code]["features"] += 1
        except Exception as ex:
            stats[code]["note"] = "拉伸失败"
            log("【%s】轮廓 %d 拉伸失败: %s" % (code, fi, ex))
            continue
        got = _bodies_of(feat)
        if op is None:
            bodies.extend(got)
        if role == "target" and got:
            regions.append((got[0], prof["outer"]["bbox"]))

        for k, hole in enumerate(holes):
            hc = chain_curves(hole)
            if hc is None:
                continue
            if op is not None:
                hop = ("unite", pick)
                hname = base_name + "_CORE%d" % k
            else:
                host = got[0] if got else None
                if host is None:
                    continue
                hop = ("subtract", host)
                hname = base_name + "_H%d" % k
            try:
                extrude_curves(work_part, hc, start, end, hname,
                               bool_op=hop, help_pt=chain_help(hole))
                stats[code]["features"] += 1
            except Exception as ex:
                stats[code]["note"] = "孔处理失败"
                log("【%s】轮廓 %d 孔 %d 处理失败: %s" % (code, fi, k, ex))

    if role == "target":
        log("【%s】基准体完成: %d 个轮廓(体 %d 个), %.4g→%.4g。"
            % (code, len(profiles), len(regions), start, end))
    elif role == "subtract":
        log("【%s】布尔减完成: %d 个轮廓(从 FLB 减去)。" % (code, len(profiles)))
    else:
        log("【%s】拉伸完成: %d 个轮廓。" % (code, len(profiles)))
    stats[code]["bodies"] = bodies
    return bodies, regions
