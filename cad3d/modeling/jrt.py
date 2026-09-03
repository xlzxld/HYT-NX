# -*- coding: utf-8 -*-
"""cad3d.modeling.jrt —— 加热条 (JRT) 双侧建模、G1 相切边倒圆与删面愈合。"""

import math
from cad3d.core.constants import (
    DEFAULT_JRT, TARGET_CODE, FEATURE_PREFIX, LAYER_CODES
)
from cad3d.core.logging import _fmt_num
from cad3d.modeling.nx_compat import _mark_curve, _bodies_of
from cad3d.modeling.purge import _CREATED_FEATURES
from cad3d.modeling.extrude import _sc_rule_options, extrude_curves
from cad3d.modeling.stdparts import _pick_target, _bool_feature
from cad3d.geom.topo import (
    find_chains, _merge_open_chains, _chain_connectors, _chain_outlet_mids
)
from cad3d.geom.eval import (
    _faces_healthy, _dome_body_ok, _blend_ok, _conn_face_pick, _jrt_sides
)


def _uf_face_data(uf, face):
    """UF.Modeling.AskFaceData → 7 元组 (type, point[3], dir[3], bbox[6], r, ratio, norm)。"""
    return uf.Modeling.AskFaceData(face.Tag)


def _find_flat_face(uf, body, z_plane, tol=0.6):
    """找法向±Z 且位于 z_plane 的平面(条端面)。"""
    try:
        faces = list(body.GetFaces())
    except Exception:
        return None
    best, bd = None, None
    for f in faces:
        try:
            d = _uf_face_data(uf, f)
            if float(d[4]) < 1e-9 and abs(d[2][2]) > 0.999:
                dist = abs(d[1][2] - z_plane)
                if dist < tol and (best is None or dist < bd):
                    best, bd = f, dist
        except Exception:
            continue
    return best


def _edge_blend_end(work_part, uf, body, z_plane, radius, log, feat_name=None):
    """端面外边 G1 相切边倒圆(期刊同款规则 OuterEdgesOfFaces+LaminarEdge 与标志)。"""
    import NXOpen
    import NXOpen.Features

    face = _find_flat_face(uf, body, z_plane)
    if face is None:
        log("  倒圆: 未找到 z=%.3f 端面" % z_plane)
        return None, []
    try:
        before = set(f.Tag for f in body.GetFaces())
    except Exception:
        before = set()

    bldr = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        sc = work_part.ScCollectors.CreateCollector()
        opts = _sc_rule_options(work_part)
        if opts is not None:
            try:
                rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face], opts)
            except TypeError:
                rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
            try:
                opts.Dispose()
            except Exception:
                pass
        else:
            rule = work_part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
        sc.ReplaceRules([rule], False)
        try:
            sc.AddEvaluationFilter(NXOpen.ScEvaluationFiltertype.LaminarEdge)
        except Exception:
            pass

        for _pn, _pv in (("Tolerance", 0.01), ("AllInstancesOption", False),
                         ("RemoveSelfIntersection", True),
                         ("PatchComplexGeometryAreas", True),
                         ("LimitFailingAreas", True)):
            try:
                setattr(bldr, _pn, _pv)
            except Exception:
                pass
        try:
            bldr.ConvexConcaveY = False
            bldr.RollOverSmoothEdge = True
            bldr.RollOntoEdge = True
            bldr.MoveSharpEdge = True
            bldr.TrimmingOption = False
            bldr.OverlapOption = \
                NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
            bldr.BlendOrder = \
                NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
            bldr.SetbackOption = \
                NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
            bldr.BlendFaceContinuity = \
                NXOpen.Features.EdgeBlendBuilder.FaceContinuity.Tangent
        except Exception:
            pass
        bldr.AddChainset(sc, _fmt_num(radius))
        feat = bldr.CommitFeature()
        if feat_name:
            try:
                feat.SetName(feat_name)
            except Exception:
                pass
        _CREATED_FEATURES.append(feat)
        try:
            new_faces = [f for f in body.GetFaces() if f.Tag not in before]
        except Exception:
            new_faces = []
        return feat, new_faces
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _body_face_rows(uf, body):
    """条体全部面 → [(类型, 半径, bbox零维数), ...](体检用)。"""
    rows = []
    for f in body.GetFaces():
        try:
            d = uf.Modeling.AskFaceData(f.Tag)
            bb = d[3]
            zc = sum(1 for a, b in ((bb[0], bb[3]), (bb[1], bb[4]),
                                    (bb[2], bb[5])) if b - a <= 0.01)
            rows.append((int(d[0]), float(d[4]), zc))
        except Exception:
            continue
    return rows


def _body_volume(work_part, body):
    """体积(MeasureManager.NewMassProperties, 期刊签名 5 单位; 失败回 None)。"""
    try:
        mm = work_part.MeasureManager
        unit_mm = work_part.UnitCollection.FindObject("MilliMeter")
        try:
            mp = mm.NewMassProperties([unit_mm] * 5, 0.99, [body])
            try:
                try:
                    return float(mp.Volume())
                except Exception:
                    return float(mp.Volume)
            finally:
                if hasattr(mp, "Dispose"):
                    try:
                        mp.Dispose()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            return float(body.Volume)
        except Exception:
            pass
    except Exception:
        pass
    return None


def _edge_blend_end_retry(session, work_part, uf, body, z_plane,
                          r0, r_min, r_step, log, feat_name, label,
                          dome=False):
    """带异形检测的端面倒圆: R 从 r0 起, 异形/失败撤销降 R 重试。"""
    import NXOpen
    r = float(r0)
    step = max(float(r_step), 1e-4)
    while r >= float(r_min) - 1e-9:
        mark = session.SetUndoMark(
            NXOpen.Session.MarkVisibility.Invisible, "CAD3D JRT试倒圆")
        v0 = _body_volume(work_part, body)
        try:
            feat, nf = _edge_blend_end(work_part, uf, body, z_plane, r, log,
                                       feat_name=feat_name)
        except Exception:
            feat, nf = None, []
        v1 = _body_volume(work_part, body) if feat is not None else None
        okh = True
        why = ""
        if feat is not None:
            rows_all = _body_face_rows(uf, body)
            okh, why = _faces_healthy(rows_all)
            if okh and dome:
                okh, why = _dome_body_ok(rows_all)
        if feat is not None and _blend_ok(v0, v1) and okh:
            if v0 is not None and v1 is not None and v0 > 0:
                log("  %s 倒圆R%.4g 体积%.1f→%.1f 面体检通过。"
                    % (label, r, v0, v1))
            return feat, nf, r
        if feat is not None and not _blend_ok(v0, v1):
            log("  %s 倒圆R%.4g 体积异常(%.1f→%.1f), 撤销降R重试。"
                % (label, r, v0, v1))
        elif feat is not None:
            log("  %s 倒圆R%.4g 面体检不过(%s), 撤销降R重试。" % (label, r, why))
        try:
            session.UndoToMark(mark, None)
        except Exception:
            pass
        r -= step
    return None, [], float(r0)


def _delete_faces(work_part, faces, log, feat_name=None):
    """同步建模删除面(期刊 DeleteFaceBuilder Type=Face, 删除后自动愈合)。"""
    import NXOpen
    import NXOpen.Features

    faces = [f for f in faces if f is not None]
    if not faces:
        return None
    bldr = work_part.Features.CreateDeleteFaceBuilder(NXOpen.Features.Feature.Null)
    try:
        bldr.Type = NXOpen.Features.DeleteFaceBuilder.SelectTypes.Face
        opts = _sc_rule_options(work_part)
        if opts is not None:
            try:
                rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces), opts)
            except TypeError:
                rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
            try:
                opts.Dispose()
            except Exception:
                pass
        else:
            rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
        bldr.FaceCollector.ReplaceRules([rule], False)
        feat = bldr.Commit()
        if feat_name:
            try:
                feat.SetName(feat_name)
            except Exception:
                pass
        _CREATED_FEATURES.append(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _delete_faces_safe(session, work_part, uf, body, faces, log,
                       feat_name, label):
    """带体检的删面: 整组删→体检→撤销; 逐片删→体检→撤销; 都失败保留倒圆面。"""
    import NXOpen
    faces = [f for f in faces if f is not None]
    if not faces:
        return False
    pre20 = sum(1 for t, _r, _z in _body_face_rows(uf, body) if t == 20)

    def _del_ok():
        rows = _body_face_rows(uf, body)
        okh, why = _faces_healthy(rows)
        if not okh:
            return False, why
        n20 = sum(1 for t, _r, _z in rows if t == 20)
        if n20 > pre20:
            return False, "样条补丁面+%d" % (n20 - pre20)
        return True, ""

    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                               "CAD3D 删面试删")
    try:
        _delete_faces(work_part, faces, log, feat_name=feat_name)
    except Exception as ex:
        log("  %s 整组删被 NX 拒绝(%s), 转单片试删。" % (label, ex))
    else:
        okh, why = _del_ok()
        if okh:
            return True
        log("  %s 整组删面后出现%s, 撤销转单片试删。" % (label, why))
    try:
        session.UndoToMark(mark, None)
    except Exception:
        pass

    done = False
    for f in faces:
        mark2 = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                    "CAD3D 删面试删单片")
        try:
            _delete_faces(work_part, [f], log, feat_name=feat_name)
        except Exception:
            try:
                session.UndoToMark(mark2, None)
            except Exception:
                pass
            continue
        okh2, why2 = _del_ok()
        if okh2:
            done = True
        else:
            log("  %s 单片删后出现%s, 撤销该片。" % (label, why2))
            try:
                session.UndoToMark(mark2, None)
            except Exception:
                pass
    if done:
        log("  %s 整组删面愈合失败, 已改单片删(部分保留)。" % label)
        return True
    log("  %s 删面愈合均产生碎片/样条补丁, 已全部撤销——保留倒圆面。"
        % label)
    return False


def _pick_conn_faces(uf, faces, conn_mids, r_ref=None, log=None):
    """每个收口连接线中点各取最近的 1 个倒圆面(删面对象)。"""
    rows = []
    for f in faces:
        try:
            d = _uf_face_data(uf, f)
            cx = (d[3][0] + d[3][3]) / 2.0
            cy = (d[3][1] + d[3][4]) / 2.0
            rows.append((f.Tag, cx, cy, float(d[4])))
        except Exception:
            continue
    tags = _conn_face_pick(rows, conn_mids, r_ref)
    if tags is None:
        if log:
            log("  删面放弃: 连接线附近未找到半径匹配的倒圆面"
                "(r_ref=%s), 保留倒圆面。" % _fmt_num(r_ref or 0.0))
        return []
    by_tag = {f.Tag: f for f in faces}
    return [by_tag[t] for t in tags if t in by_tag]


def _set_display(session, objs, color, translucency):
    """对象显示修改(颜色+透明度, 期刊 DisplayModification 同款)。"""
    if not objs:
        return
    dm = None
    try:
        dm = session.DisplayManager.NewDisplayModification()
        dm.ApplyToAllFaces = True
        dm.ApplyToOwningParts = False
        dm.NewColor = int(color)
        dm.NewTranslucency = int(translucency)
        dm.Apply(list(objs))
    except Exception:
        pass
    finally:
        if dm is not None:
            try:
                dm.Dispose()
            except Exception:
                pass


def build_jrt(session, work_part, layers, nx_curves, flb_regions, params, jp,
              log, stats):
    """阶段 7: JRT 加热条建模(两侧对称直建, 等效期刊的 镜像→切槽→删镜像→再镜像)。"""
    import NXOpen
    import NXOpen.UF

    stats["JRT"] = {"curves": len(layers.get("JRT") or []), "profiles": 0,
                    "features": 0, "bodies": [], "note": ""}
    z_start = float(jp.get("start", 0.0))
    z_end = float(jp.get("end", 0.0))
    log("【JRT】生效参数: 起始=%.4g 结束=%.4g 边倒圆R=%.4g 步长=%.4g R下限=%.4g"
        % (z_start, z_end, jp.get("blend_r", 3.9), jp.get("r_step", 0.1),
           jp.get("r_min", 3.7)))
    if abs(z_end - z_start) <= 1e-9:
        stats["JRT"]["note"] = "起始=结束, 停用"
        log("【JRT】起始=结束(零宽度), 停用。")
        return []
    ents = layers.get("JRT") or []
    if not ents:
        stats["JRT"]["note"] = "图层无曲线"
        log("【JRT】图层无曲线, 跳过。")
        return []
    closed, opens = find_chains(ents)
    bridge_map = {}
    if opens:
        c_extra, b_jobs, o_logs = _merge_open_chains(opens, ents)
        closed = list(closed) + c_extra
        for _chain, pairs in b_jobs:
            bridge_map[id(_chain)] = pairs
            closed.append(_chain)
            for p1, p2, gap in pairs:
                log("【JRT】开口链(%d 段)缺口 %.3f mm, 将自动桥接闭合。"
                    % (len(_chain), gap))
        for nseg, tips in o_logs:
            log("【JRT】警告: 开链 %d 段无法自动闭合(断口 %s), 跳过——"
                "请检查 2D 图 JRT 轮廓。" % (nseg, tips))
        if not c_extra and not b_jobs:
            log("【JRT】警告: %d 条开口链未参与建模。" % len(opens))
    if not closed:
        stats["JRT"]["note"] = "无封闭链"
        log("【JRT】无封闭链(需 jrt_runner 完整流程输出), 跳过。")
        return []
    if not flb_regions:
        stats["JRT"]["note"] = "无 FLB 基准体"
        log("【JRT】无 FLB 基准体, 跳过。")
        return []

    uf = NXOpen.UF.UFSession.GetUFSession()
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    top, bottom = max(s, e), min(s, e)
    offset = float(jp.get("offset", DEFAULT_JRT["offset"]))
    draft = float(jp.get("draft", DEFAULT_JRT["draft"]))
    if draft <= 1e-9:
        draft = None

    strips = []
    for ci, chain in enumerate(closed):
        idxs = [i for i, _r in chain]
        curves = [nx_curves["JRT"][i] for i in idxs]
        if any(c is None for c in curves):
            log("【JRT】链 %d 含创建失败曲线, 跳过。" % (ci + 1))
            continue
        br = bridge_map.get(id(chain))
        if br:
            try:
                for p1, p2, _gap in br:
                    bridge_line = work_part.Curves.CreateLine(
                        NXOpen.Point3d(p1[0], p1[1], 0.0),
                        NXOpen.Point3d(p2[0], p2[1], 0.0))
                    _mark_curve(bridge_line)
                    curves.append(bridge_line)
            except Exception as ex:
                log("【JRT】链 %d 桥接线创建失败: %s" % (ci + 1, ex))
                continue
        if not idxs:
            continue
        pts = []
        for i in idxs:
            ent = ents[i]
            pts.append(ent.p1 if ent.kind != "circle" else ent.c)
        cx = (sum(p[0] for p in pts) / len(pts)) if pts else 0.0
        cy = (sum(p[1] for p in pts) / len(pts)) if pts else 0.0
        first = ents[idxs[0]]
        hp = NXOpen.Point3d(first.p1[0] if first.kind != "circle" else first.c[0],
                            first.p1[1] if first.kind != "circle" else first.c[1], 0.0)
        conns = _chain_connectors(chain, ents)
        if not conns:
            log("【JRT】链 %d 未识别收口连接线, 删面锚点改用出线口线中点。"
                % (ci + 1))

        for side, z_flush, z_embed in _jrt_sides(z_start, z_end, bottom):
            base = "%sJRT_%d%s" % (FEATURE_PREFIX, ci + 1, side)
            zlo, zhi = min(z_flush, z_embed), max(z_flush, z_embed)
            off = (offset, 0.0) if z_flush > z_embed else (0.0, offset)
            try:
                feat = extrude_curves(work_part, curves, zlo, zhi, base,
                                      help_pt=hp, offset=off, draft=draft)
                stats["JRT"]["features"] += 1
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 拉伸失败: %s" % (ci + 1, side, ex))
                continue
            bodies = _bodies_of(feat)
            if not bodies:
                log("【JRT】链 %d 侧 %s 无实体, 跳过。" % (ci + 1, side))
                continue
            body = bodies[0]

            r_min_all = float(jp.get("r_min", 3.7))
            try:
                _f, new_faces, _r_used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_embed,
                    float(jp["blend_r"]), r_min_all,
                    max(float(jp.get("r_step", 0.1)), 1e-6), log,
                    base + "_BLE", "链%d侧%s嵌入端" % (ci + 1, side))
                if _f is not None:
                    stats["JRT"]["features"] += 1
                    _dm = _chain_outlet_mids(chain, ents) or conns
                    if _dm and len(new_faces) > 2:
                        if _delete_faces_safe(session, work_part, uf, body,
                                              _pick_conn_faces(uf, new_faces,
                                                               _dm,
                                                               r_ref=_r_used,
                                                               log=log),
                                              log, base + "_DELE",
                                              "链%d侧%s嵌入端删面" % (ci + 1, side)):
                            stats["JRT"]["features"] += 1
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 嵌入端倒圆失败: %s" % (ci + 1, side, ex))

            target = _pick_target(flb_regions, cx, cy, log=log)
            if target is not None:
                try:
                    _bool_feature(work_part, "subtract", target, [body],
                                  base + "_SUB", log, retain_tools=True)
                    stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【JRT】链 %d 侧 %s 相减失败: %s" % (ci + 1, side, ex))

            _r_start = float(jp["blend_r"])
            try:
                _f2, nf2, used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_flush,
                    _r_start, r_min_all,
                    max(float(jp.get("r_step", 0.1)), 1e-6), log,
                    base + "_BLF", "链%d侧%s齐平端" % (ci + 1, side),
                    dome=True)
                if _f2 is not None:
                    stats["JRT"]["features"] += 1
                    if abs(used - _r_start) > 1e-9:
                        log("【JRT】链 %d 侧 %s 齐平端倒圆降半径至 %.4g。"
                            % (ci + 1, side, used))
                else:
                    log("【JRT】链 %d 侧 %s 齐平端倒圆全部失败(下限 %.4g), "
                        "触发兜底: 回退到出线端删面完成状态(此端保留直角)。"
                        % (ci + 1, side, r_min_all))
            except Exception as ex:
                log("【JRT】链 %d 侧 %s 齐平端倒圆异常: %s" % (ci + 1, side, ex))
                used, nf2 = _r_start, []

            _dm = _chain_outlet_mids(chain, ents) or conns
            if _dm and len(nf2) > 2:
                try:
                    if _delete_faces_safe(session, work_part, uf, body,
                                          _pick_conn_faces(uf, nf2, _dm,
                                                           r_ref=used, log=log),
                                          log, base + "_DELF",
                                          "链%d侧%s圆顶删面" % (ci + 1, side)):
                        stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【JRT】链 %d 侧 %s 圆顶删面失败: %s" % (ci + 1, side, ex))

            strips.append(body)
            stats["JRT"]["profiles"] += 1

    _set_display(session, strips, jp.get("color_strip", 186), jp.get("translucency", 50))
    model_bodies = []
    seen = set(id(b) for b in strips)
    for body, _b in flb_regions:
        if id(body) not in seen:
            model_bodies.append(body)
            seen.add(id(body))
    for code in LAYER_CODES:
        for body in (stats.get(code, {}).get("bodies") or []):
            if id(body) not in seen:
                model_bodies.append(body)
                seen.add(id(body))
    _set_display(session, model_bodies, jp.get("color_model", 78),
                 jp.get("translucency", 50))

    stats["JRT"]["bodies"] = strips
    log("【JRT】完成: %d 条链 × 两侧 = %d 根加热条, 特征 %d 个。"
        % (len(closed), len(strips), stats["JRT"]["features"]))
    return strips
