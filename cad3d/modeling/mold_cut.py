# -*- coding: utf-8 -*-
"""cad3d.modeling.mold_cut —— 模具自动开框: 冲突试切(可配)与布尔减去。

前提(用户工作流, 2026-09 澄清): 分层拉伸流水线已由 nx_extrude_runner.py 跑完
(产物体带 CAD3D_TYPE 类型标记), 模具已由用户手动放置到工作部件中。

流程: 工具体(带 CAD3D 标记)与模具体(未标记体, 含装配组件自动提升)包围盒
接触处布尔减去, 工具体保留; 同一模具体命中的全部工具体攒成一批一次减
(整批失败自动回退逐个减, 结果不变, 大幅减少布尔刷新次数)。试切受总开关
MOLD_TRIAL_CUT 控制(默认开):
关闭时全部直接减去; 开启时对 conflict_check 配置的类型减前先试切对比目标体
附近的曲面孔壁——孔壁消失/缩小=会破坏模具已有孔, 撤销并跳过该件
(用户案例: 螺丝放在模具孔边缘, 直接减会把螺丝槽与孔打通, 两孔俱废)。

【已搁置】按类后处理(2026-09-07): B 出线槽(CX)台阶边/天侧开口边倒圆,
C 中心定位片等减后删碎面+孔壁偏置扩孔。代码保留但默认不配置不执行,
启用方式见 nx_std_config.py 的 MOLD_CUT_RULES 注释。

类型识别: 体属性 CAD3D_TYPE(流水线打标: "CX"/"FLB"/"JT"/"JRT"/"STD:文件名");
无标记的旧版产物按空类型处理(默认不查冲突不做后处理), 重跑流水线可获得标记。
"""

import math

from cad3d.core.constants import (
    COMP_PREFIX,
    FEATURE_PREFIX,
    MOLD_AUDIT_VOLUME,
    MOLD_BBOX_TOL,
    MOLD_CUT_RULES,
    MOLD_TRIAL_CUT,
)
from cad3d.core.logging import _fmt_num
from cad3d.modeling.jrt import (
    _body_volume,
    _delete_faces,
    _edge_blend_end_retry,
    _uf_face_data,
)
from cad3d.modeling.nx_compat import _is_marked, _iter, _type_of
from cad3d.modeling.purge import _CREATED_FEATURES
from cad3d.modeling.stdparts import _bool_feature, _promote_body

# ============================================================================
# 纯逻辑(可离线测)
# ============================================================================

def _merge_face_bboxes(rows):
    """多张面的 6 元组包围盒 [(x0,y0,z0,x1,y1,z1),...] → 合并包围盒; 空/残缺→None。"""
    bb = None
    for r in rows or []:
        if r is None or len(r) < 6:
            continue
        try:
            v = [float(r[0]), float(r[1]), float(r[2]),
                 float(r[3]), float(r[4]), float(r[5])]
        except (TypeError, ValueError):
            continue
        if bb is None:
            bb = v
        else:
            for i in range(3):
                bb[i] = min(bb[i], v[i])
                bb[i + 3] = max(bb[i + 3], v[i + 3])
    return tuple(bb) if bb is not None else None


def _bbox_overlap(a, b, tol=0.05):
    """6 元组包围盒是否重叠(含贴面接触; tol 为各向放宽量 mm)。残缺输入→False。"""
    if not a or not b or len(a) < 6 or len(b) < 6:
        return False
    try:
        for i in range(3):
            if float(a[i]) > float(b[i + 3]) + tol:
                return False
            if float(b[i]) > float(a[i + 3]) + tol:
                return False
        return True
    except (TypeError, ValueError):
        return False


def _grow(bb, m):
    """包围盒各向外扩 m(mm); 残缺→None。"""
    if not bb or len(bb) < 6:
        return None
    return (float(bb[0]) - m, float(bb[1]) - m, float(bb[2]) - m,
            float(bb[3]) + m, float(bb[4]) + m, float(bb[5]) + m)


def _extents(bb):
    """包围盒三向尺寸 (dx, dy, dz); 残缺→(0,0,0)。"""
    if not bb or len(bb) < 6:
        return (0.0, 0.0, 0.0)
    return (float(bb[3]) - float(bb[0]), float(bb[4]) - float(bb[1]),
            float(bb[5]) - float(bb[2]))


def _is_sliver(bb, sliver_max):
    """薄片碎面判定: 最薄维≤阈值 且 次薄维≤2×阈值(孔底大面不误判)。"""
    e = sorted(_extents(bb))
    return e[0] <= float(sliver_max) and e[1] <= 2.0 * float(sliver_max)


def _body_matches_bbox(bb, target, tol):
    """体包围盒与目标尺寸逐向匹配(中心定位片等按尺寸找体)。残缺→False。"""
    if not bb or not target or len(bb) < 6 or len(target) < 3:
        return False
    e = _extents(bb)
    try:
        return all(abs(e[i] - float(target[i])) <= float(tol) for i in range(3))
    except (TypeError, ValueError):
        return False


def _kw_hits(kw, type_key):
    """STD: 关键词行是否命中类型键(其余键只做精确匹配)。"""
    if kw.startswith("STD:") and type_key.startswith("STD:"):
        return kw[4:] in type_key
    return False


def _rule_for(type_key, rules):
    """类型键 → 合并规则: 类型默认 < STD:关键词(按表序) < 精确匹配。

    类型默认: STD:*(标准件, 小型件)conflict_check=True; 其余大腔体 False。
    """
    merged = {"conflict_check": type_key.startswith("STD:")}
    for kw, r in rules or []:
        if kw != type_key and _kw_hits(kw, type_key):
            merged.update(r)
    for kw, r in rules or []:
        if kw == type_key:
            merged.update(r)
            break
    return merged


def _hole_rows(face_rows):
    """面行中只留曲面(孔壁候选; 行[2]=半径>1e-9)。"""
    out = []
    for r in face_rows or []:
        try:
            if float(r[2]) > 1e-9:
                out.append(r)
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _broken_holes(before, after, tol_r=0.15, tol_c=1.0, tol_ext=1.0):
    """试切前后孔壁对比 → 被破坏的 before 行列表。

    行格式: (face, type, 半径, cx, cy, cz, bbox6)。匹配: 同半径(±tol_r)且中心
    最近(≤tol_c); 匹配上但任一向尺寸缩水>tol_ext 也算破坏(孔壁被吃掉一块)。
    找不到匹配=整面被吃(与口袋打通)。纯逻辑, 可离线测。
    """
    after_left = list(after or [])
    broken = []
    for b in before or []:
        best, bd = None, None
        for a in after_left:
            try:
                if abs(float(a[2]) - float(b[2])) > tol_r:
                    continue
            except (TypeError, ValueError, IndexError):
                continue
            d = math.sqrt((float(a[3]) - float(b[3])) ** 2
                          + (float(a[4]) - float(b[4])) ** 2
                          + (float(a[5]) - float(b[5])) ** 2)
            if best is None or d < bd:
                best, bd = a, d
        if best is None or bd > tol_c:
            broken.append(b)
            continue
        eb, ea = _extents(b[6]), _extents(best[6])
        if any(eb[i] - ea[i] > tol_ext for i in range(3)):
            broken.append(b)
            continue
        after_left.remove(best)
    return broken


def _fmt_bbox(bb):
    if not bb or len(bb) < 6:
        return "?"
    return "(%.2f,%.2f,%.2f)-(%.2f,%.2f,%.2f)" % tuple(bb[:6])


def _fmt_center(bb):
    """包围盒 XY 中心(日志定位用); 残缺→"?"。"""
    if not bb or len(bb) < 6:
        return "?"
    return "%.1f,%.1f" % ((bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0)


# ============================================================================
# NX 依赖
# ============================================================================

def _face_rows(uf, body, region=None, margin=0.0):
    """体面行 [(face, 类型, 半径, cx, cy, cz, bbox6)]; region 给定时只留相交面。"""
    out = []
    try:
        faces = list(body.GetFaces())
    except Exception:
        return out
    for f in faces:
        try:
            d = _uf_face_data(uf, f)
            r = float(d[4])
            bb = tuple(float(x) for x in d[3])
            if region is not None and not _bbox_overlap(bb, region, margin):
                continue
            out.append((f, int(d[0]), r,
                        (bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0,
                        (bb[2] + bb[5]) / 2.0, bb))
        except Exception:
            continue
    return out


# 体级包围盒 UF 接口探测顺序: 仅 Exact(精确轴对齐盒)。近似版
# AskBoundingBox 基于多边形略偏小, 贴面接触在 0.05mm 容差下可能漏判, 不用。
_BBOX_ASK_NAMES = ("AskBoundingBoxExact",)
_bbox_diag = [False]          # 首體/首回退诊断只打一次


def _body_bbox(uf, body, log=None):
    """体包围盒: 体级 UF 一次调用优先(比逐面询查快一个数量级), 失败回退逐面合并。

    回退兜底保证任何 NX 版本行为不变; 首次生效/回退时打一行诊断日志
    (回退时枚举本 NX UF.Modeling 含 'bound' 的接口名), 供跨版本适配取证。
    """
    for name in _BBOX_ASK_NAMES:
        ask = getattr(uf.Modeling, name, None)
        if ask is None:
            continue
        try:
            bb = tuple(float(x) for x in ask(body.Tag)[:6])
            if len(bb) == 6:
                if not _bbox_diag[0]:
                    _bbox_diag[0] = True
                    if log is not None:
                        log("  包围盒: 一次调用就拿到了(%s), 走的快路径。" % name)
                return bb
        except Exception:
            continue
    if not _bbox_diag[0]:
        _bbox_diag[0] = True
        if log is not None:
            names = sorted(n for n in dir(uf.Modeling)
                           if "bound" in n.lower())
            log("  包围盒: 本 NX 没有 %s 这个包装, 改成逐面合并(结果一样, 慢些);"
                " 本机含 'bound' 的 UF 接口: %s。"
                % ("/".join(_BBOX_ASK_NAMES), ", ".join(names) or "无"))
    rows = []
    try:
        faces = list(body.GetFaces())
    except Exception:
        return None
    for f in faces:
        try:
            rows.append(_uf_face_data(uf, f)[3])
        except Exception:
            continue
    return _merge_face_bboxes(rows)


def _pair_hits(tool_bb, mold_bbs, tol=0.05):
    """工具体包围盒 → 命中的模具下标列表(包围盒重叠预筛)。纯逻辑, 可离线测。"""
    out = []
    if tool_bb and len(tool_bb) >= 6:
        for mi, mbb in enumerate(mold_bbs or []):
            if _bbox_overlap(tool_bb, mbb, tol):
                out.append(mi)
    return out


def _pick_points(pts, cap=16, region=None):
    """采样点去重(0.001mm 网格), region(bbox6)内的点优先, 超出 cap 截断。

    纯逻辑, 可离线测; 残缺点跳过。
    """
    seen = set()
    uniq = []
    for p in pts or []:
        try:
            k = (round(float(p[0]), 3), round(float(p[1]), 3),
                 round(float(p[2]), 3))
        except (TypeError, ValueError, IndexError):
            continue
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    cap = max(1, int(cap))
    if region is not None and len(uniq) > cap:
        inside = [p for p in uniq if _bbox_overlap(p + p, region, 0.0)]
        in_set = set(inside)
        picked = list(inside)
        for p in uniq:
            if len(picked) >= cap:
                break
            if p not in in_set:
                picked.append(p)
        return picked
    return uniq[:cap]


def _body_vertices(body, cap=16, region=None):
    """体棱边端点采样(顶点集): 去重, region(模具 bbox)内的点优先, 上限 cap。

    失败/无棱边→[]。
    """
    pts = []
    try:
        edges = list(body.GetEdges())
    except Exception:
        return []
    for e in edges:
        try:
            for p in (e.StartPoint, e.EndPoint):
                pts.append((p.X, p.Y, p.Z))
        except Exception:
            continue
    return _pick_points(pts, cap, region)


def _any_point_inside(contains, body, pts):
    """任一采样点落在体材料内→True; 全部在体外→False。

    单点查询异常不计; 查询全部失败/无点→True(保守: 无证据不剔除)。纯逻辑。
    """
    queried = 0
    for p in pts or []:
        try:
            queried += 1
            if contains(body, p):
                return True
        except Exception:
            queried -= 1
            continue
    return queried == 0


# 点在体内判定 UF 包装候选(UF_MODL_ask_point_containment 系列, 跨版本探测)
_POINT_IN_NAMES = ("AskPointContainment",)


def _ask_point_response(ask, body, pt, trace=None):
    """调用点包含接口, 归一化 response 整数; 签名探测链全失败→None。

    首选签名 ask([x,y,z], body_tag)->response 为 NX 实机验证(2026-09-08
    活性探针: 返回 2=点在体表面); 其余为跨版本后备。
    trace 非 None(list) 时记录每个签名的尝试结果(诊断/取证用)。
    """
    pt3 = [float(pt[0]), float(pt[1]), float(pt[2])]
    tag = getattr(body, "Tag", None)
    calls = (lambda: ask(pt3, tag),
             lambda: ask(tag, pt3),
             lambda: ask(tag, pt3[0], pt3[1], pt3[2]),
             lambda: ask([tag], pt3),
             lambda: ask(1, [tag], pt3))
    for i, call in enumerate(calls, 1):
        try:
            r = call()
        except TypeError as ex:
            if trace is not None:
                trace.append("签名#%d TypeError(不符): %s" % (i, ex))
            continue
        except Exception as ex:
            if trace is not None:
                trace.append("签名#%d %s: %s" % (i, type(ex).__name__, ex))
            return None
        if isinstance(r, tuple):
            r = r[0] if r else None
        try:
            r = int(r)
        except (TypeError, ValueError):
            if trace is not None:
                trace.append("签名#%d 返回不可解析: %r" % (i, r))
            return None
        if trace is not None:
            trace.append("签名#%d 成功 response=%d" % (i, r))
        return r
    return None


def _get_point_contains(uf, mold_rows, log):
    """探测"点在体内"接口, 以"明确外部点"的 response 为外参照自校准语义。

    不臆测 response 常量表: bbox 内缩采样点须有与外参照不同的值(证明
    可区分内外), 否则校准失败禁用。探测/校准任一失败返回 None(调用方
    禁用预筛, 行为回退现状), 并留诊断日志。
    """
    ask = None
    for name in _POINT_IN_NAMES:
        ask = getattr(uf.Modeling, name, None)
        if ask is not None:
            break
    if ask is None:
        return None
    outside_val = None
    diag = []
    for mb, bb, _v in mold_rows:
        if not bb or min(_extents(bb)) <= 1.0:
            continue
        ex, ey, ez = _extents(bb)
        r_out = _ask_point_response(ask, mb, (bb[0] - ex - 10.0,
                                              bb[1] - ey - 10.0,
                                              bb[2] - ez - 10.0), diag)
        if r_out is None:
            continue
        distinct = False
        n_same = 0
        for fx in (0.3, 0.5, 0.7):
            for fy in (0.3, 0.5, 0.7):
                for fz in (0.3, 0.5, 0.7):
                    r = _ask_point_response(
                        ask, mb, (bb[0] + ex * fx, bb[1] + ey * fy,
                                  bb[2] + ez * fz))
                    if r is None:
                        continue
                    if r != r_out:
                        distinct = True
                        break
                    n_same += 1
                if distinct:
                    break
            if distinct:
                break
        if distinct:
            outside_val = r_out
            break
        diag.append("内点 %d 个 response 均与外部点(%d)同值" % (n_same, r_out))
    if outside_val is None:
        log("  悬空件预筛: 校准没过, 关掉。诊断: %s"
            % ("; ".join(diag[:4]) if diag else "没有可用来校准的模具"))
        return None

    def contains(body, pt):
        r = _ask_point_response(ask, body, pt)
        if r is None:
            raise RuntimeError("point containment query failed")
        return r != outside_val

    return contains


def _collect_mold(session, work_part, log):
    """模具体收集: 部件内未标记体优先; 为空时提升非 CAD3D 装配组件。

    返回模具体列表。组件方式放置的模具: 提升体后移除组件引用(标准件同款,
    提升体不受影响), 避免组件与提升体双重显示。
    """
    bodies = [b for b in _iter(work_part.Bodies) if not _is_marked(b)]
    if bodies:
        return bodies
    import NXOpen as nx

    root = work_part.ComponentAssembly.RootComponent
    if root is None:
        return []
    comps = []
    try:
        for c in root.GetChildren():
            if not str(getattr(c, "Name", "")).startswith(COMP_PREFIX):
                comps.append(c)
    except Exception as ex:
        log("【模具】读取装配组件失败: %s" % ex)
        return []
    if not comps:
        return []
    log("【模具】部件里没有独立实体, 但有 %d 个不是脚本放的装配组件, 当作你手动"
        "放的模具: 把里面的实体提升上来, 再去掉组件引用(和标准件同一套做法, "
        "可以整体撤销)。" % len(comps))
    out = []
    for c in comps:
        got = _promote_body(work_part, c, "%sBODY_MOLD" % FEATURE_PREFIX,
                            log, body_index=None) or []
        out.extend(b for b in got if b is not None)
        try:
            session.UpdateManager.AddToDeleteList([c])
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible,
                                    "CAD3D 删模具组件引用"))
        except Exception as ex:
            log("  模具组件引用没删掉(提升上来的实体不受影响): %s" % ex)
    return out


def _conflict_check(session, work_part, uf, tool, tool_bbox, target, log):
    """试切对比孔壁: 返回 (是否冲突, 被破坏孔行列表)。试切后撤销还原。

    只看工具体附近(外扩 2mm)的曲面孔壁; 平面 pocket 壁不保护(大腔体正常切)。
    """
    region = _grow(tool_bbox, 2.0)
    before = _hole_rows(_face_rows(uf, target, region))
    import NXOpen
    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                               "CAD3D 冲突试切")
    fs = _bool_feature(work_part, "subtract", target, [tool],
                       "%sTRIAL" % FEATURE_PREFIX, log, retain_tools=False)
    broken = []
    if fs:
        after = _hole_rows(_face_rows(uf, target, region))
        broken = _broken_holes(before, after)
    for f in (fs or []):                        # 撤销后登记表不留死引用
        try:
            _CREATED_FEATURES.remove(f)
        except Exception:
            pass
    try:
        session.UndoToMark(mark, None)
    except Exception:
        pass
    return bool(broken), broken


def _top_face_z(uf, body):
    """体最高水平面 Z(天侧); 找不到→None。"""
    z = None
    for row in _face_rows(uf, body):
        bb = row[6]
        try:
            if row[2] < 1e-9 and (bb[5] - bb[2]) <= 0.01 \
                    and (z is None or bb[2] > z):
                z = bb[2]
        except (TypeError, ValueError, IndexError):
            continue
    return z


def _select_flush_edges(target, tb, z_top, tol_z=0.5):
    """天侧开口边: 端点都在 z_top 且中点落在槽 footprint 内的直边(3 边 U 形)。"""
    sel = []
    try:
        edges = list(target.GetEdges())
    except Exception:
        return sel
    for e in edges:
        try:
            p1, p2 = e.StartPoint, e.EndPoint
            if abs(float(p1.Z) - z_top) > tol_z \
                    or abs(float(p2.Z) - z_top) > tol_z:
                continue
            mx = (float(p1.X) + float(p2.X)) / 2.0
            my = (float(p1.Y) + float(p2.Y)) / 2.0
            if tb[0] - 1.0 <= mx <= tb[3] + 1.0 \
                    and tb[1] - 1.0 <= my <= tb[4] + 1.0:
                sel.append(e)
        except Exception:
            continue
    return sel


def _blend_edges(work_part, edges, radius, log, feat_name):
    """对显式边列表倒圆(规则名跨版本探测; 失败返回 False 并留日志)。"""
    import NXOpen
    import NXOpen.Features

    edges = [e for e in edges if e is not None]
    if not edges:
        return False
    rule = None
    mk = getattr(work_part.ScRuleFactory, "CreateRuleEdgeDumb", None)
    if mk is not None:
        for args in ((list(edges),), (list(edges), None)):
            try:
                rule = mk(*args)
                break
            except Exception:
                rule = None
    if rule is None:
        log("  天侧圆角: 这个 NX 版本没有 CreateRuleEdgeDumb 边规则(想让脚本"
            "探一下的话, 把 nx_mold_cut_runner.py 的 MODE 改成 \"api\"), 跳过。")
        return False
    bldr = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        sc = work_part.ScCollectors.CreateCollector()
        sc.ReplaceRules([rule], False)
        try:
            sc.AddEvaluationFilter(NXOpen.ScEvaluationFiltertype.LaminarEdge)
        except Exception:
            pass
        bldr.AddChainset(sc, _fmt_num(radius))
        feat = bldr.CommitFeature()
        try:
            feat.SetName(feat_name)
        except Exception:
            pass
        _CREATED_FEATURES.append(feat)
        return True
    except Exception as ex:
        log("  天侧圆角没做成(%s), 跳过。" % ex)
        return False
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def _blend_channel(session, work_part, uf, target, tb, rule, log):
    """出线槽(CX)减后倒圆: 槽底台阶边走 JRT 端面倒圆; 天侧开口边走边规则。"""
    r_step = float(rule.get("blend_step_r") or 0.0)
    r_flush = float(rule.get("blend_flush_r") or 0.0)
    if r_step > 0:
        try:
            feat, _nf, used = _edge_blend_end_retry(
                session, work_part, uf, target, tb[2], r_step,
                max(1.0, r_step - 1.0), 0.25, log,
                "%sMOLD_CXSTEP" % FEATURE_PREFIX, "出线槽台阶边")
            if feat is not None and abs(used - r_step) > 1e-9:
                log("  出线槽台阶边圆角改小到 R%.4g 才做成。" % used)
        except Exception as ex:
            log("  出线槽台阶边圆角出错: %s" % ex)
    if r_flush > 0:
        z_top = _top_face_z(uf, target)
        if z_top is None:
            log("  没找到模具的水平顶面, 天侧圆角跳过。")
            return
        edges = _select_flush_edges(target, tb, z_top)
        log("  天侧待倒圆的边有 %d 条(高度 z=%.3f)。" % (len(edges), z_top))
        if edges:
            _blend_edges(work_part, edges, r_flush, log,
                         "%sMOLD_CXTOP" % FEATURE_PREFIX)


def _clearance_hole(session, work_part, uf, target, tb, cfg, log):
    """减后扩孔(中心定位片等): 删孔内薄片碎面 → 孔壁向外偏置放大间隙。"""
    sliver_max = float(cfg.get("sliver_max", 5.0))
    offset = float(cfg.get("offset", 0.0))
    region = _grow(tb, 1.0)
    rows = _face_rows(uf, target, region)
    curved = [r for r in rows if r[2] > 1e-9]
    if not curved:
        log("  把孔放大: 这块区域内没找到孔壁曲面, 跳过。")
        return
    main = max(curved, key=lambda r: max(_extents(r[6])))
    slivers = [r for r in rows
               if r is not main and _is_sliver(r[6], sliver_max)]
    if slivers:
        _delete_faces(work_part, [r[0] for r in slivers], log,
                      "%sMOLD_CUTSLIVER" % FEATURE_PREFIX)
        log("  把孔放大: 先删掉孔里的碎面 %d 片。" % len(slivers))
    walls = [r[0] for r in _hole_rows(_face_rows(uf, target, region))]
    if offset > 0:
        n = _offset_faces(work_part, walls, offset, log,
                          "%sMOLD_OFF" % FEATURE_PREFIX)
        if n:
            log("  把孔放大: %d 个孔壁往外偏了 %.4g。" % (n, offset))


def _offset_faces(work_part, faces, offset, log, feat_name):
    """偏置面(向外放大孔); 构造器名跨版本探测, 失败返回 0 并留日志。"""
    import NXOpen
    import NXOpen.Features

    faces = [f for f in faces if f is not None]
    if not faces:
        return 0
    bldr = None
    for mk_name in ("CreateOffsetFaceBuilder", "CreateOffsetBuilder"):
        mk = getattr(work_part.Features, mk_name, None)
        if mk is not None:
            try:
                bldr = mk(NXOpen.Features.Feature.Null)
                break
            except Exception:
                bldr = None
    if bldr is None:
        log("  把孔放大: 这个 NX 版本没有 OffsetFace 构造器(想让脚本探一下的"
            "话, 把 nx_mold_cut_runner.py 的 MODE 改成 \"api\"), 跳过。")
        return 0
    try:
        opts = None
        mk_opts = getattr(work_part.ScRuleFactory, "CreateRuleOptions", None)
        if mk_opts is not None:
            try:
                opts = mk_opts()
            except Exception:
                opts = None
        rule = None
        mk_rule = getattr(work_part.ScRuleFactory, "CreateRuleFaceDumb", None)
        if mk_rule is not None:
            for args in ((list(faces), opts), (list(faces),)):
                try:
                    rule = mk_rule(*args)
                    break
                except Exception:
                    rule = None
        if rule is None:
            log("  把孔放大: 选面的规则没建成, 跳过。")
            return 0
        coll = getattr(bldr, "FaceCollector", None)
        if coll is None:
            coll = getattr(bldr, "Faces", None)
        if coll is None:
            log("  把孔放大: 构造器上找不到面收集器, 跳过。")
            return 0
        coll.ReplaceRules([rule], False)
        dist = getattr(bldr, "Distance", None)
        if dist is not None:
            from cad3d.modeling.nx_compat import _set_expr
            _set_expr(dist, _fmt_num(offset))
        feat = None
        for commit in ("CommitFeature", "Commit"):
            cm = getattr(bldr, commit, None)
            if cm is not None:
                try:
                    feat = cm()
                    break
                except Exception:
                    feat = None
        if feat is None:
            log("  把孔放大: 提交没成功, 跳过。")
            return 0
        try:
            feat.SetName(feat_name)
        except Exception:
            pass
        _CREATED_FEATURES.append(feat)
        return len(faces)
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def cut_mold(session, work_part, log, bbox_tol=None, rules=None, stats=None,
             trial_cut=None):
    """模具自动开框主入口: 冲突试切(可配)+布尔减去; B/C 后处理已搁置(默认关)。

    trial_cut: 试切总开关; None=取配置 MOLD_TRIAL_CUT(默认开)。关闭时全部
    类型直接减去; 开启时按 rules 里各类型 conflict_check 决定是否减前试切。
    返回统计 dict(ok/tools/mold/cuts/skip/fail/conflict/post), 写入 stats["MOLD"]。
    任何异常整体回滚到进入前状态并返回 ok=False。
    """
    import time
    import traceback

    import NXOpen
    import NXOpen.UF

    t0 = time.time()
    t_trial = 0.0
    t_cut = 0.0
    if stats is None:
        stats = {}
    st = {"ok": False, "tools": 0, "mold": 0, "cuts": 0, "skip": 0, "fail": 0,
          "conflict": 0, "post": 0}
    stats["MOLD"] = st
    tol = MOLD_BBOX_TOL if bbox_tol is None else float(bbox_tol)
    if rules is None:
        rules = MOLD_CUT_RULES
    if trial_cut is None:
        trial_cut = MOLD_TRIAL_CUT
    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                               "CAD3D 模具开框")
    try:
        uf = NXOpen.UF.UFSession.GetUFSession()
        tools = [b for b in _iter(work_part.Bodies) if _is_marked(b)]
        mold = _collect_mold(session, work_part, log)
        st["tools"], st["mold"] = len(tools), len(mold)
        n_untyped = sum(1 for t in tools if not _type_of(t))
        if n_untyped:
            log("【模具开框】提醒: %d 个实体没有类型标记(旧版脚本的产物), "
                "按默认规则处理; 重跑一遍拉伸流水线就会有标记。" % n_untyped)
        log("【模具开框】脚本产物实体 %d 个, 模具体 %d 个(没有 CAD3D 标记的), "
            "接触容差 %.4g, 规则 %d 条, 试切%s。"
            % (len(tools), len(mold), tol, len(rules),
               "开(MOLD_TRIAL_CUT=True)" if trial_cut
               else "关(MOLD_TRIAL_CUT=False, 全部直接减)"))
        if not tools or not mold:
            log("【模具开框】中止: %s。请确认分层拉伸流水线跑完了, 且模具已经"
                "手动放到工作部件里。"
                % ("没有脚本产出的实体" if not tools else "没找到模具体"))
            return st

        mold_rows = []
        for i, mb in enumerate(mold):
            bb = _body_bbox(uf, mb, log)
            v = _body_volume(work_part, mb) if MOLD_AUDIT_VOLUME else None
            mold_rows.append((mb, bb, v))
            if v is not None:
                log("  模具#%d 包围盒=%s 体积=%.1f" % (i + 1, _fmt_bbox(bb), v))
            else:
                log("  模具#%d 包围盒=%s" % (i + 1, _fmt_bbox(bb)))

        # ── 阶段 A1: 冲突试切(逐工具, 只判不减) → A2 按模具攒批一次减 ──
        mold_bbs = [row[1] for row in mold_rows]
        contains = _get_point_contains(uf, mold_rows, log)
        if contains is not None:
            log("  悬空件检查: 用实体顶点判断是否真碰到模具, 悬空的直接跳过。")
        else:
            log("  悬空件检查: 本 NX 没有可用的判断接口或校准没过, 自动关掉。")
        pending = {}                  # 模具下标 → [(t, tb, tkey, rule, tlabel)]
        for ti, t in enumerate(tools):
            tb = _body_bbox(uf, t, log)
            tkey = _type_of(t)
            rule = _rule_for(tkey, rules)
            tlabel = "实体#%d[%s](中心 %s)" % (ti + 1, tkey or "?",
                                              _fmt_center(tb))
            tpts = _body_vertices(t, 16) if contains is not None else []
            hits = _pair_hits(tb, mold_bbs, tol)
            if not hits:
                st["skip"] += 1
                continue
            for mi in hits:
                if contains is not None and tpts and \
                        not _any_point_inside(contains, mold_rows[mi][0], tpts):
                    st["skip"] += 1
                    log("  跳过: %s 跟模具#%d 其实没碰上(采样的顶点全在模具"
                        "外面, 悬空的不参与挖)。" % (tlabel, mi + 1))
                    continue
                if trial_cut and rule.get("conflict_check"):
                    _ta = time.time()
                    bad, broken = _conflict_check(session, work_part, uf,
                                                  t, tb, mold_rows[mi][0], log)
                    t_trial += time.time() - _ta
                    if bad:
                        st["conflict"] += 1
                        log("  跳过: %s 挖进模具#%d 会碰坏 %d 处已有的孔"
                            "(试挖已经撤销), 这里就不挖了。"
                            % (tlabel, mi + 1, len(broken)))
                        for b in broken:
                            log("    会碰坏的孔: R=%.3f 中心(%.1f,%.1f,%.1f)"
                                % (b[2], b[3], b[4], b[5]))
                        continue
                pending.setdefault(mi, []).append((t, tb, tkey, rule, tlabel))

        # ── 阶段 A2: 每模具体批量减(合并调用失败自动降级逐个, 失败名单对账) ──
        cut_plan = []
        _seen = set()
        for mi in sorted(pending):
            mb = mold_rows[mi][0]
            batch = pending[mi]
            ts = [it[0] for it in batch]
            multi = len(ts) > 1
            if multi:
                log("  一次挖 %d 件: 模具#%d ← %s。"
                    % (len(ts), mi + 1,
                       "、".join(it[4].split("(")[0] for it in batch)))
            _tc = time.time()
            _fs, failed = _bool_feature(
                work_part, "subtract", mb, ts,
                "%sMOLDCUT_%d" % (FEATURE_PREFIX, mi + 1),
                log, retain_tools=True, with_failed=True, session=session)
            t_cut += time.time() - _tc
            _fail_ids = {id(t) for t in failed}
            n_ok = len(ts) - len(failed)
            st["cuts"] += n_ok
            st["fail"] += len(failed)
            if multi:
                if not failed:
                    log("  挖好了: 模具#%d ← %d 件一次挖成。" % (mi + 1, len(ts)))
                elif not n_ok:
                    log("  没挖成: 模具#%d ← %d 件全失败(没真正相交, 或者"
                        "几何不成)。" % (mi + 1, len(ts)))
                else:
                    log("  挖了 %d 件: 模具#%d ← %d 件中 %d 件成功, %d 件失败"
                        "跳过。" % (n_ok, mi + 1, len(ts), n_ok, len(failed)))
            elif n_ok:
                log("  挖好了: %s → 模具#%d。" % (batch[0][4], mi + 1))
            else:
                log("  没挖成: %s → 模具#%d(没真正相交, 或者几何不成), 跳过。"
                    % (batch[0][4], mi + 1))
            for it in batch:
                if id(it[0]) in _fail_ids or id(it[0]) in _seen:
                    continue
                _seen.add(id(it[0]))
                cut_plan.append((it[0], it[1], it[2], it[3], mb))

        # ── 阶段 B/C: 按类后处理(倒圆/扩孔)【已搁置: 默认不配置即不执行】──
        for t, tb, tkey, rule, target in cut_plan:
            if rule.get("blend_step_r") or rule.get("blend_flush_r"):
                log("【后处理】%s: 给出线槽倒圆。" % (tkey or "?"))
                _blend_channel(session, work_part, uf, target, tb, rule, log)
                st["post"] += 1
            cl = rule.get("clearance")
            if isinstance(cl, dict):
                log("【后处理】%s: 把孔放大一点(先删碎面再往外偏置)。"
                    % (tkey or "?"))
                _clearance_hole(session, work_part, uf, target, tb, cl, log)
                st["post"] += 1

        n_changed = 0
        t_audit = 0.0
        if MOLD_AUDIT_VOLUME:
            _ta = time.time()
            for mi, (mb, _bb, v0) in enumerate(mold_rows):
                v1 = _body_volume(work_part, mb)
                if v0 is not None and v1 is not None and abs(v0 - v1) > 1e-6:
                    log("  对账: 模具#%d 体积 %.1f → %.1f (挖掉 %.1f)。"
                        % (mi + 1, v0, v1, v0 - v1))
                    n_changed += 1
            t_audit = time.time() - _ta
        st["ok"] = True
        msg = ("【模具开框】完成: 脚本实体 %d 个, 挖了 %d 处, 不接触跳过 %d, "
               "没挖成 %d, 怕碰坏孔跳过 %d 处, 后处理 %d 件"
               % (st["tools"], st["cuts"], st["skip"], st["fail"],
                  st["conflict"], st["post"]))
        if MOLD_AUDIT_VOLUME:
            msg += ", 体积有变化的模具 %d 块" % n_changed
        msg += "。耗时: 总 %.1f 秒(试挖 %.1f / 挖 %.1f / 对账 %.1f)。"
        log(msg % (time.time() - t0, t_trial, t_cut, t_audit))
        return st
    except Exception as ex:
        log("【模具开框】出错: %s" % ex)
        log("【堆栈】%s" % traceback.format_exc())
        try:
            session.UndoToMark(mark, "CAD3D 模具开框回滚")
            log("【回滚】这次模具开框的改动已全部撤销。")
        except Exception as ex2:
            log("【回滚失败】%s" % ex2)
        return st
