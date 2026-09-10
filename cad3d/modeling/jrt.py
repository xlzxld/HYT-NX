# -*- coding: utf-8 -*-
"""cad3d.modeling.jrt —— 加热条 (JRT) 双侧建模、G1 相切边倒圆与删面愈合。

图纸约定(2026-09-10 用户定案, 3.dxf 实测): 一根加热条画两圈线——
  ① 最内侧与最外侧那条(首尾相接成闭合轮廓, 含 2 条 8mm 封口线): **建模用**;
  ② 中间那条(可能多条)是量加热条长度用的中心线: **不参与建模**
     (拉伸它会多长一条), 它一般两头不相接, 于是被判成"两条没接上、
     跳过不建模"——这是正常现象, 不是图纸缺线。2.dxf/26079/3.dxf 全是这个
     结构。
JRTFBX(加热条封闭线标记)图层: 用户画线优先定位出线口(即删面位置);
  短线取中点、横跨画的长线取两端点, 8mm 封口线的中点就是锚点所在。
  标记就近分配到条, 离条超限或与轮廓推断明显不符的自动剔除(不剔除会让
  一处画歪就整根条不删面)。无标记的条自动走轮廓推断, 不因缺标记而不删面
  (v2.7 CXK 教训)。
v2.8/v2.9: 只认轮廓推断时, 删面锚点按条自身封闭轮廓辨认出线口唇线
  (_contour_outlet_mids 开放性判别)——旧"最短两条线"规则会选中槽底封口线
  (2.dxf 实证), 删面因此一直定错端。
日志文案口径(2026-09-10): 面向操作者用大白话, 坐标/尺寸/R 值照原样保留。
"""

import math
from cad3d.core.constants import (
    DEFAULT_JRT, TARGET_CODE, FEATURE_PREFIX, LAYER_CODES
)
from cad3d.core.logging import _fmt_num
from cad3d.modeling.nx_compat import _mark_curve, _mark_type, _bodies_of
from cad3d.modeling.purge import _CREATED_FEATURES
from cad3d.modeling.extrude import _sc_rule_options, extrude_curves
from cad3d.modeling.stdparts import _pick_target, _bool_feature
from cad3d.geom.topo import (
    find_chains, _merge_open_chains, _merge_marker_lines, _chain_connectors,
    _chain_outlet_mids, _contour_outlet_mids, _bbox, _fbx_anchor_points,
    _marker_mids_for_chains
)
from cad3d.geom.eval import (
    _faces_healthy, _dome_body_ok, _blend_ok, _conn_face_pick, _jrt_sides,
    _flush_blend_allowed
)


def _fmt_xy(pts):
    """点列表 → "(x,y)/(x,y)"(日志用); 空 → "无"。"""
    return "/".join("(%.1f,%.1f)" % (p[0], p[1]) for p in pts) or "无"


# 一根条最多 2 个出线口, 每个口最多 2 条标记线(横跨画的长线取两端点)——超过
# 这个数的标记视为画多了, 只取离出线口最近的几条。
_FBX_MAX = 4


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
        log("  圆角: 没找到高度 %.3f 处的端面" % z_plane)
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
                log("  %s: R%.4g 圆角做成(体积 %.1f→%.1f, 面检查正常)。"
                    % (label, r, v0, v1))
            return feat, nf, r
        if feat is not None and not _blend_ok(v0, v1):
            log("  %s: R%.4g 时体积不对(%.1f→%.1f), 撤销, 换小一点再试。"
                % (label, r, v0, v1))
        elif feat is not None:
            log("  %s: R%.4g 时面不对(%s), 撤销, 换小一点再试。" % (label, r, why))
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
        log("  %s: 一次全删被 NX 拒绝(%s), 改成一片一片删。" % (label, ex))
    else:
        okh, why = _del_ok()
        if okh:
            return True
        log("  %s: 全删后%s, 撤销, 改成一片一片删。" % (label, why))
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
            log("  %s: 这片删了会%s, 撤销这片。" % (label, why2))
            try:
                session.UndoToMark(mark2, None)
            except Exception:
                pass
    if done:
        log("  %s: 一次全删不行, 改成一片一片删(只删成功了部分)。" % label)
        return True
    log("  %s: 怎么删都会留下碎片, 已全部撤销——圆角面保留。" % label)
    return False


def _pick_conn_faces(uf, faces, conn_mids, r_ref=None, log=None):
    """每个删面锚点(中点)各取最近的 1 个倒圆面(删面对象); 锚点 v2.7 起
    优先取 CXK 出线口图层坐标。"""
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
            log("  出线口附近没找到半径 R%s 的圆角面, 为免删错这次不删面。"
                % _fmt_num(r_ref or 0.0))
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
                    "features": 0, "bodies": [], "note": "", "skip_flush": 0}
    z_start = float(jp.get("start", 0.0))
    z_end = float(jp.get("end", 0.0))
    log("【加热条】本次参数: 嵌入端 %.4g→%.4g, 圆角 R%.4g 起、做不成就按 %.4g "
        "往下减、最小 R%.4g。"
        % (z_start, z_end, jp.get("blend_r", 3.9), jp.get("r_step", 0.1),
           jp.get("r_min", 3.7)))
    if abs(z_end - z_start) <= 1e-9:
        stats["JRT"]["note"] = "起始=结束, 停用"
        log("【加热条】起始和结束一样(厚度为 0), 不做。")
        return []
    ents = list(layers.get("JRT") or [])
    if not ents:
        stats["JRT"]["note"] = "该层没有线"
        log("【加热条】JRT 层上没有线条, 跳过。")
        return []
    # JRTFBX(标记层)并入条轮廓: 老图纸槽口在 JRT 层张开, 要靠 JRTFBX 那几条
    # 线把缺口封上才能闭合成条; 新图纸 JRT 层自己已闭合, 标记线与 JRT 线完全
    # 重合就不重复拼(防双重描线坏链)。下标一律用标记层里的原始下标, 否则
    # JRTFBX 混进弧/圆时取到的曲线会错位。重合丢弃的条数记账, 不再静默。
    _fbx_all = list(layers.get("JRTFBX") or [])
    _fbx_curves = list(nx_curves.get("JRTFBX") or [])
    _add_idx, _dup_idx, _ = _merge_marker_lines(ents, _fbx_all)
    _added, _lost = 0, 0
    for _k in _add_idx:
        _cv = _fbx_curves[_k] if _k < len(_fbx_curves) else None
        if _cv is None:
            _lost += 1
            log("【加热条】标记线 %d 没画出来, 这条没能拼进条轮廓。" % (_k + 1))
            continue
        ents.append(_fbx_all[_k])
        nx_curves.setdefault("JRT", []).append(_cv)
        _added += 1
    if _fbx_all:
        _n_line = len(_add_idx) + len(_dup_idx)
        if _added:
            log("【加热条】标记层有 %d 条线, 其中 %d 条拼进了条轮廓(补上槽口的缺口)。"
                % (_n_line, _added))
        if _dup_idx:
            log("【加热条】标记层有 %d 条线跟 JRT 层的线完全重合, 没重复拼——"
                "条体外形仍按 JRT 层的线做, 这些线只用来定出线口的位置。"
                % len(_dup_idx))
        if _lost:
            log("【加热条】标记层有 %d 条线没能画出来(见上), 不影响条体外形。"
                % _lost)
    closed, opens = find_chains(ents)
    bridge_map = {}
    if opens:
        c_extra, b_jobs, o_logs = _merge_open_chains(opens, ents)
        closed = list(closed) + c_extra
        for _chain, pairs in b_jobs:
            bridge_map[id(_chain)] = pairs
            closed.append(_chain)
            for p1, p2, gap in pairs:
                log("【加热条】有条线差 %.3fmm 没接上(%d 段), 自动补上。"
                    % (gap, len(_chain)))
        for nseg, tips in o_logs:
            log("【加热条】有 %d 段线两头没接上, 跳过不建模。中间那条中心线"
                "(量长度用)本来就两头不相接, 属正常; 若是外形缺线, 请回 2D 图补齐。"
                "断口 %s。" % (nseg, tips))
        if not c_extra and not b_jobs:
            log("【加热条】有 %d 条线没能用上(两头没接上), 说明见上。"
                % len(opens))
    if not closed:
        stats["JRT"]["note"] = "没有闭合的条轮廓"
        log("【加热条】没找到闭合的条轮廓, 跳过——请确认 JRT 层最内侧和最外侧"
            "那两条线首尾相接。")
        return []
    if not flb_regions:
        stats["JRT"]["note"] = "没有分流板基准体"
        log("【加热条】没有分流板基准体, 跳过。")
        return []

    uf = NXOpen.UF.UFSession.GetUFSession()
    s, e = params.get(TARGET_CODE, (0.0, 0.0))
    top, bottom = max(s, e), min(s, e)
    offset = float(jp.get("offset", DEFAULT_JRT["offset"]))
    draft = float(jp.get("draft", DEFAULT_JRT["draft"]))
    if draft <= 1e-9:
        draft = None

    # v2.10 JRTFBX(加热条封闭线)标记: 用户画线优先定位出线口。标记就近
    # 分配到条(离条超 10mm 视为画错, 忽略+告警); 无标记的条自动走轮廓
    # 推断——标记只是优先锚点, 不复刻 v2.7 CXK"缺标记即不删面"的错。
    fbx_pts = _fbx_anchor_points(layers.get("JRTFBX"))
    fbx_per, fbx_ignore = [], []
    if fbx_pts:
        _boxes = []
        for ch in closed:
            ps = []
            for i, _r in ch:
                e = ents[i]
                if e.kind == "circle":
                    ps += [(e.c[0] - e.r, e.c[1] - e.r),
                           (e.c[0] + e.r, e.c[1] + e.r)]
                else:
                    ps += [e.p1, e.p2]
            for p1, p2, _g in (bridge_map.get(id(ch)) or []):
                ps += [p1, p2]
            _boxes.append(_bbox(ps))
        fbx_per, fbx_ignore = _marker_mids_for_chains(_boxes, fbx_pts, 10.0)
        for w in fbx_ignore:
            log("【加热条】%s。" % w)
    _gate = 2.5 * max(float(jp["blend_r"]), 1.0) + 2.0

    strips = []
    for ci, chain in enumerate(closed):
        idxs = [i for i, _r in chain]
        curves = [nx_curves["JRT"][i] for i in idxs]
        if any(c is None for c in curves):
            log("【加热条】第 %d 根: 有线没画出来, 这根跳过。" % (ci + 1))
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
                log("【加热条】第 %d 根: 补缺口的那条线没画出来(%s), 这根跳过。"
                    % (ci + 1, ex))
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
        # 出线口(要删面的位置): 标记层优先(用户画的), 没标记就按轮廓自己认。
        # 轮廓推断同时当"参照"用来剔除画歪的标记——不剔除的话, 一个画歪的
        # 标记会让整根条一个面都不删(下游是"有一个位置找不到对应面就整组
        # 放弃")。全部标记都对不上时保留标记(用户画线优先), 只提示核对。
        _infer = (_chain_outlet_mids(chain, ents)
                  or _contour_outlet_mids(chain, ents) or conns)
        _fbx = list(fbx_per[ci]) if fbx_per else []
        _dm = []
        if _fbx:
            _keep = [m for m in _fbx
                     if not _infer
                     or min(math.hypot(m[0] - v[0], m[1] - v[1])
                            for v in _infer) <= _gate]
            if _infer and not _keep:
                _keep = list(_fbx)
                log("【加热条】第 %d 根: 标记位置和轮廓算出来的出线口对不上"
                    "(差 %.1f 以上), 仍按标记删面, 请核对图纸上的标记。"
                    % (ci + 1, _gate))
            elif _infer:
                for _m in _fbx:
                    if _m not in _keep:
                        log("【加热条】第 %d 根: 标记 (%.1f,%.1f) 离出线口太远"
                            "(超过 %.1f), 已忽略。" % (ci + 1, _m[0], _m[1], _gate))
            _dm = _keep
            if len(_dm) > _FBX_MAX:
                if _infer:
                    _dm.sort(key=lambda m: min(
                        math.hypot(m[0] - v[0], m[1] - v[1]) for v in _infer))
                log("【加热条】第 %d 根: 标记有 %d 处, 只取离出线口最近的 %d 处。"
                    % (ci + 1, len(_dm), _FBX_MAX))
                _dm = _dm[:_FBX_MAX]
            log("【加热条】第 %d 根: 出线口按图纸标记定, %d 处 %s。"
                % (ci + 1, len(_dm), _fmt_xy(_dm)))
        else:
            _dm = list(_infer)
            if _dm:
                log("【加热条】第 %d 根: 图纸上没有标记, 出线口按轮廓自己认, "
                    "%d 处 %s。" % (ci + 1, len(_dm), _fmt_xy(_dm)))
            else:
                log("【加热条】第 %d 根: 认不出出线口在哪, 这根不删面。" % (ci + 1))

        for side, z_flush, z_embed in _jrt_sides(z_start, z_end, bottom):
            base = "%sJRT_%d%s" % (FEATURE_PREFIX, ci + 1, side)
            _who = "第 %d 根%s侧" % (ci + 1, "上" if side == "T" else "下")
            zlo, zhi = min(z_flush, z_embed), max(z_flush, z_embed)
            off = (offset, 0.0) if z_flush > z_embed else (0.0, offset)
            try:
                feat = extrude_curves(work_part, curves, zlo, zhi, base,
                                      help_pt=hp, offset=off, draft=draft)
                stats["JRT"]["features"] += 1
            except Exception as ex:
                log("【加热条】%s: 拉伸失败(%s), 这段跳过。" % (_who, ex))
                continue
            bodies = _bodies_of(feat)
            if not bodies:
                log("【加热条】%s: 没生成实体, 跳过。" % _who)
                continue
            body = bodies[0]

            r_min_all = float(jp.get("r_min", 3.7))
            r_step_all = max(float(jp.get("r_step", 0.1)), 1e-6)
            embed_ok = False
            try:
                _f, new_faces, _r_used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_embed,
                    float(jp["blend_r"]), r_min_all, r_step_all, log,
                    base + "_BLE", "%s嵌入端" % _who)
                if _f is not None:
                    stats["JRT"]["features"] += 1
                    if _dm and len(new_faces) > 2:
                        if _delete_faces_safe(session, work_part, uf, body,
                                              _pick_conn_faces(uf, new_faces,
                                                               _dm,
                                                               r_ref=_r_used,
                                                               log=log),
                                              log, base + "_DELE",
                                              "%s嵌入端删面" % _who):
                            stats["JRT"]["features"] += 1
                            embed_ok = True      # 倒圆+出线口删面双双成功
                    else:
                        embed_ok = True          # 无删面锚点: 仅倒圆不算失败
            except Exception as ex:
                log("【加热条】%s: 嵌入端圆角失败(%s)。" % (_who, ex))

            target = _pick_target(flb_regions, cx, cy, log=log)
            if target is not None:
                try:
                    _bool_feature(work_part, "subtract", target, [body],
                                  base + "_SUB", log, retain_tools=True)
                    stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【加热条】%s: 切进分流板失败(%s)。" % (_who, ex))

            if not _flush_blend_allowed(embed_ok):
                stats["JRT"]["skip_flush"] += 1
                log("【加热条】%s: 嵌入端圆角或删面没做成, 齐平端就不倒圆了"
                    "(这端留直角)。" % _who)
            else:
                _r_start = float(jp["blend_r"])
                try:
                    _f2, nf2, used = _edge_blend_end_retry(
                        session, work_part, uf, body, z_flush,
                        _r_start, r_min_all, r_step_all, log,
                        base + "_BLF", "%s齐平端" % _who,
                        dome=True)
                    if _f2 is not None:
                        stats["JRT"]["features"] += 1
                        if abs(used - _r_start) > 1e-9:
                            log("【加热条】%s: 齐平端圆角改小到 R%.4g 才做成。"
                                % (_who, used))
                    else:
                        log("【加热条】%s: 齐平端圆角做到 R%.4g 还不行, "
                            "这端留直角。" % (_who, r_min_all))
                except Exception as ex:
                    log("【加热条】%s: 齐平端圆角出错(%s)。" % (_who, ex))
                    used, nf2 = _r_start, []

                if _dm and len(nf2) > 2:
                    try:
                        if _delete_faces_safe(session, work_part, uf, body,
                                              _pick_conn_faces(uf, nf2, _dm,
                                                               r_ref=used,
                                                               log=log),
                                              log, base + "_DELF",
                                              "%s圆顶删面" % _who):
                            stats["JRT"]["features"] += 1
                    except Exception as ex:
                        log("【加热条】%s: 圆顶删面失败(%s)。" % (_who, ex))

            _mark_type(body, "JRT")
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
    log("【加热条】完成: 图纸上 %d 根条 → 上下各一条共 %d 根实体, 特征 %d 个%s。"
        % (len(closed), len(strips), stats["JRT"]["features"],
           (", 其中 %d 根因嵌入端没做成、齐平端留了直角"
            % stats["JRT"]["skip_flush"])
           if stats["JRT"]["skip_flush"] else ""))
    return strips
