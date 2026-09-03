# -*- coding: utf-8 -*-
"""
nx_jrt.py —— JRT 加热条 NX 工序(拉伸/倒圆重试/删面/切槽/圆顶/着色)
========================================================================

拆分自 nx_extrude_runner.py(§5.6 JRT 工序函数)。工序依据用户期刊
journal.py 反推, 样板 3Djrttest.prt 为验收基准:
  每条闭合链 × 板两侧: 拉伸(壁偏置+拔模, 齐平端→入侵端) → 嵌入端 G1 边倒圆
  → 删远端 2 个倒圆面 → 保件相减切槽 → 齐平端倒圆(失败降半径) → 删远端 2 面
  (圆顶) → 着色。

依赖契约(由主脚本注入, 见 docs/模块拆分实施计划.md): NXOpen 在函数内延迟
import(本模块 import 时不触发 NX); 判据函数来自 nx_jrt_geom, 建模助手来自
主脚本(extrude_curves/_bool_feature/_pick_target/_mark_curve/_fmt_num/
_sc_rule_options/_bodies_of/registry)与常量(DEFAULT_JRT/TARGET_CODE/
LAYER_CODES/FEATURE_PREFIX)及 nx_geom.find_chains。
"""


def _uf_face_data(uf, face):
    """UF.Modeling.AskFaceData → 7 元组 (type, point[3], dir[3], bbox[6], r, ratio, norm)。"""
    return uf.Modeling.AskFaceData(face.Tag)


def _find_flat_face(uf, body, z_plane, tol=0.6):
    """找法向±Z 且位于 z_plane 的平面(条端面)。

    v1.17: tol 0.05→0.6 并取容差内最近面——桥接截面的条拔模+壁偏置
    会让端面整体偏 ±offset×tan(拔模)(实测 ±0.34), 按精确 z 找不到端面
    → 该条两端直角无倒圆一案。
    """
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
    """端面外边 G1 相切边倒圆(期刊同款规则 OuterEdgesOfFaces+LaminarEdge 与标志)。

    返回 (feature, 新增面列表); 失败返回 (None, [])。
    """
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
                pass                          # 旧版缺该属性则跳过, 不整条崩
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
        registry.add(feat)
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


def _body_volume(work_part, body):
    """体积(MeasureManager.NewMassProperties, 期刊签名 5 单位; 失败回
    None → 调用侧不拦截)。"""
    try:
        mm = work_part.MeasureManager
        unit_mm = work_part.UnitCollection.FindObject("MilliMeter")
        try:
            mp = mm.NewMassProperties([unit_mm] * 5, 0.99, [body])
            try:
                return float(mp.Volume())
            except Exception:
                return float(mp.Volume)
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
    """带异形检测的端面倒圆: R 从 r0 起, 每轮先记撤销标记, 倒圆后体积
    校验(_blend_ok)+碎片体检(_faces_healthy); dome=True(齐平端)追加
    圆顶判据(_dome_body_ok: 体内残留型20样条面=异形, v1.27 定案)。
    异形/失败 → UndoToMark 撤销 → R-=r_step 重试到 r_min(用户工序)。
    返回 (feature, 新面列表, 实际用到的R); 全失败 → (None, [], r0)。"""
    import NXOpen
    r = float(r0)
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
        r -= float(r_step)
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
        registry.add(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _delete_faces_safe(session, work_part, uf, body, faces, log,
                       feat_name, label):
    """带体检的删面: 整组删→体检(样条面/碎片=愈合失败)→撤销;
    逐片删→体检→撤销; 都失败保留倒圆面(宁可端部多两片圆角,
    也不出货变形条——出线端删面一案)。返回 是否有删动。"""
    import NXOpen
    faces = [f for f in faces if f is not None]
    if not faces:
        return False
    # 删面健康基线: 碎片面 + 型20样条面计数(愈合产生新样条补丁=毁容,
    # 01.dxf 圆顶删面一案; 嵌入端合法的 2 片拔模样条面以"不增加"保护)
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
        # NX 自身拒绝(如"剩余面无法封闭删除区域")→ 转单片回退
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
    # 逐片删(两片一起删愈合失败时, 单片可能愈合干净)
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
    """每个收口连接线中点各取最近的 1 个倒圆面(删面对象)。

    v1.17 收紧: 只认半径≈r_ref 的圆柱倒圆面 + 距离门控; 判定不可信
    返回 [](宁可保留倒圆面也不删错面——01.prt 异形条一案)。
    """
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
        if dm is not None:           # Apply 抛异常也要释放(v1.35)
            try:
                dm.Dispose()
            except Exception:
                pass


def build_jrt(session, work_part, layers, nx_curves, flb_regions, params, jp,
              log, stats):
    """阶段 7: JRT 加热条建模(两侧对称直建, 等效期刊的 镜像→切槽→删镜像→再镜像)。"""
    import NXOpen
    import NXOpen.Features
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
        # 开链修复(手动拉伸能成功而脚本判开一案): 断口贴近的链先合并,
        # 仍有 2 断口的画桥接线闭合(桥接线打标记, 重跑清理)。
        c_extra, b_jobs, o_logs = _merge_open_chains(opens, ents)
        closed = list(closed) + c_extra
        for _chain, pairs in b_jobs:
            bridge_map[id(_chain)] = pairs
            closed.append(_chain)          # 桥接链也进建模清单
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
        draft = None                      # 0 拔模不传(与不设拔模等价)

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
        # 链几何中心(XY)与 help 点
        pts = []
        for i in idxs:
            ent = ents[i]
            pts.append(ent.p1 if ent.kind != "circle" else ent.c)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        first = ents[idxs[0]]
        hp = NXOpen.Point3d(first.p1[0] if first.kind != "circle" else first.c[0],
                            first.p1[1] if first.kind != "circle" else first.c[1], 0.0)
        # 删面参考点 = 收口连接线中点(期刊同位置); 未识别时回退链信息
        conns = _chain_connectors(chain, ents)
        if not conns:
            log("【JRT】链 %d 未识别收口连接线, 删面锚点改用出线口线中点。"
                % (ci + 1))

        for side, z_flush, z_embed in _jrt_sides(z_start, z_end, bottom):
            base = "%sJRT_%d%s" % (FEATURE_PREFIX, ci + 1, side)
            zlo, zhi = min(z_flush, z_embed), max(z_flush, z_embed)
            # 壁偏置方向: 齐平端 0 / 嵌入端 offset(期刊同款; 沿 +Z 起点=低 Z 端)
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

            # 1) 嵌入端 G1 边倒圆(异形检测+撤销降R重试到 R下限)
            r_min_all = float(jp.get("r_min", 3.7))
            try:
                _f, new_faces, _r_used = _edge_blend_end_retry(
                    session, work_part, uf, body, z_embed,
                    float(jp["blend_r"]), r_min_all,
                    max(float(jp.get("r_step", 0.1)), 1e-6), log,
                    base + "_BLE", "链%d侧%s嵌入端" % (ci + 1, side))
                if _f is not None:
                    stats["JRT"]["features"] += 1
                    # 2) 删出线端倒圆面(锚点=出线口线, 跨接线回退;
                    #    半径匹配+距离门控+体检撤销)
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

            # 3) 保件相减切槽(槽形含嵌入端圆角)
            target = _pick_target(flb_regions, cx, cy, log=log)
            if target is not None:
                try:
                    _bool_feature(work_part, "subtract", target, [body],
                                  base + "_SUB", log, retain_tools=True)
                    stats["JRT"]["features"] += 1
                except Exception as ex:
                    log("【JRT】链 %d 侧 %s 相减失败: %s" % (ci + 1, side, ex))

            # 4) 齐平端倒圆——起试半径直接用边倒圆R(jp["blend_r"])。
            #    v1.26 曾改按条厚预防式起试(min(R, 条厚/2−0.05)), 但逐R
            #    对照实验证伪了"2R>条厚即异形"的前提并回退(见 _flush_start_r
            #    注释, 该函数保留未接入)。异形改由体检(_faces_healthy /
            #    _dome_body_ok) + 体积网(_blend_ok)检出后降 R 重试。
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
            # 5) 删出线端倒圆面(圆顶; 锚点=出线口线, 跨接线回退)
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

    # 6) 着色: 加热条 / 模型
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
