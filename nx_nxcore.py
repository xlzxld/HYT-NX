# -*- coding: utf-8 -*-
"""
nx_nxcore.py —— NX 建模内核(清理/建曲线/拉伸/分层建模/移除参数)
========================================================================

拆分自 nx_extrude_runner.py(§5)。NXOpen 在函数内延迟 import, 本模块 import
时不触发 NX(批量/自测模式安全)。

依赖契约(由主脚本注入, 见 docs/模块拆分实施计划.md):
  常量: SCRIPT_VERSION FEATURE_PREFIX COMP_PREFIX CHAIN_TOL MANAGED_MIN
        MANAGED_MAX LAYER_TABLE REF_LAYER_TABLE TARGET_CODE
  共享对象: registry(特征登记表, 实例在主脚本, 各子模块共享同一实例)
  nx_geom: organize_loops _nx_curve_fp dxf_fingerprints

跨版本兼容(实机探针定案, 勿凭 2312 经验改回):
  _add_to_section_compat(旧版 AddToSection 用 NXObject.Null) /
  _sc_rule_options(旧版无 CreateRuleOptions, 取不到返 None) /
  _set_expr(旧版无 Expression.SetFormula, 走 RightHandSide)。
"""


MARK_ATTR = "CAD3D"


def _mark_curve(obj):
    try:
        obj.SetAttribute(MARK_ATTR, SCRIPT_VERSION)
    except Exception:
        pass


def _is_marked(obj):
    try:
        return bool(obj.GetStringAttribute(MARK_ATTR))
    except Exception:
        return False



def _iter(coll):
    """NX 集合迭代: for-in 优先, 失败退 GetObjects()。"""
    try:
        return list(coll)
    except TypeError:
        try:
            return list(coll.GetObjects())
        except Exception:
            return []


def _bodies_of(feat):
    for getter in ("GetBodies", "GetEntities"):
        try:
            arr = getattr(feat, getter)()
            if arr:
                return [b for b in arr]
        except Exception:
            continue
    return []


def _fmt_num(v):
    return ("%.4f" % float(v)).rstrip("0").rstrip(".") or "0"


class Log(object):
    """日志收集器: 逐行进 ListingWindow(NX 内)并缓存供报告。"""
    def __init__(self, session=None):
        self.lines = []
        self.session = session
        if session is not None:
            try:
                session.ListingWindow.Open()
            except Exception:
                pass

    def __call__(self, msg):
        self.lines.append(msg)
        if self.session is not None:
            try:
                self.session.ListingWindow.WriteLine(msg)
            except Exception:
                pass


def nx_purge(session, work_part, log, dxf_layers=None, nx=None):
    """清理上一轮产物(只删自己的东西, 不碰用户图形):
    - 特征: CAD3D_ 前缀 + 本会话登记表(按所属部件过滤);
    - 已标记体: v1.9 移除参数后留下的哑体(特征已删, 按 CAD3D 属性标记
      识别; 特征删除时宿主体一并消失, 在特征/曲线/组件删除并更新后
      二次枚举, 只补删幸存的);
    - 组件: CAD3D_C_ 前缀实例;
    - 曲线: 带 CAD3D 标记属性的(任何图层); 11~70 内无标记的曲线与本次 DXF
      几何指纹比对 —— 重合=旧版(v1.2/v1.3)无标记产物, 删除重建;
      不重合=用户自有图形, 保留并警告。

    返回实际删除对象数(仅供诊断; 调用方目前忽略返回值)。

    (P0) nx: 显式传入 NXOpen 模块引用(调用方 run_pipeline 传它已 import 的)。
    此前本函数 `global NXOpen` 依赖 run_pipeline 在入口赋值全局——跨模块的
    隐式依赖, 拆分后必然断链; 缺省时自行 import, 旧调用点行为不变。
    """
    if nx is None:
        import NXOpen as nx
    feats, curves, comps = [], [], []
    try:
        for f in _iter(work_part.Features):
            if str(getattr(f, "Name", "")).startswith(FEATURE_PREFIX):
                feats.append(f)
    except Exception as ex:
        log("【清理】特征枚举失败: %s" % ex)
    # (P0) registry.take() 与原 "list(_CREATED_FEATURES) + del[:]" 等价:
    # 取走全部并清空(登记表双保险, 仅本工作部件)
    for f in registry.take():
        try:
            if f not in feats and f.OwningPart == work_part:
                feats.append(f)
        except Exception:
            pass
    try:                                            # 标准件组件实例
        root = work_part.ComponentAssembly.RootComponent
        if root is not None:                        # 纯部件(未成装配)时为 None
            for c in root.GetChildren():
                if str(getattr(c, "Name", "")).startswith(COMP_PREFIX):
                    comps.append(c)
    except Exception as ex:
        log("【清理】组件枚举失败: %s" % ex)

    # 曲线: 带标记的删; 范围内无标记的做指纹迁移匹配
    fps = dxf_fingerprints(dxf_layers)
    kept_warn = {}
    legacy = 0
    try:
        for c in _iter(work_part.Curves):
            try:
                lay = c.Layer
            except Exception:
                continue
            if _is_marked(c):
                curves.append(c)
            elif MANAGED_MAX >= lay >= MANAGED_MIN:
                fp = _nx_curve_fp(c)
                if fp is not None and fps.get(fp, 0) > 0:
                    fps[fp] -= 1                    # 旧版无标记产物 → 删除重建
                    curves.append(c)
                    legacy += 1
                else:
                    kept_warn[lay] = kept_warn.get(lay, 0) + 1
    except Exception as ex:
        log("【清理】曲线枚举失败: %s" % ex)

    if feats or curves or comps:
        try:
            session.UpdateManager.AddToDeleteList(feats + curves + comps)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "CAD3D 清理"))
        except Exception as ex:
            log("【清理】删除失败(可能有特征引用曲线): %s" % ex)
            return 0                    # 返回值=实际删除数, 未删成即 0

    # 已标记哑体: 特征删除后幸存的(移除参数轮产物), 二次枚举补删
    mbodies = []
    try:
        for b in _iter(work_part.Bodies):
            if _is_marked(b):
                mbodies.append(b)
    except Exception as ex:
        log("【清理】实体枚举失败: %s" % ex)
    if mbodies:
        try:
            session.UpdateManager.AddToDeleteList(mbodies)
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(nx.Session.MarkVisibility.Invisible, "CAD3D 清理体"))
        except Exception as ex:
            log("【清理】已标记体删除失败: %s" % ex)
            return len(feats) + len(curves) + len(comps)   # 体未删掉
    log("【清理】已删除上一轮: 特征 %d 个, 实体 %d 个, 曲线 %d 条(含旧版无标记 %d), 组件 %d 个。"
        % (len(feats), len(mbodies), len(curves), legacy, len(comps)))
    if kept_warn:
        log("【清理】警告: 图层 %s 有 %d 条不属于本脚本的曲线, 已保留"
            "(脚本曲线将与其同层混放, 建议移到图层 1~%d 或 %d 以上)。"
            % (",".join(str(k) for k in sorted(kept_warn)),
               sum(kept_warn.values()), MANAGED_MIN - 1, MANAGED_MAX + 1))
    return len(feats) + len(curves) + len(comps) + len(mbodies)


def ensure_categories(work_part, layer_map, log):
    """为各导入图层建同名图层类别(便于用户在图层设置里按名开关)。"""
    cats = getattr(work_part, "LayerCategories", None)
    if cats is None:
        return
    for code, num in sorted(layer_map.items(), key=lambda kv: kv[1]):
        try:
            if cats.FindObject(code) is None:
                cats.CreateCategory(code, "%s (CAD3D)" % code, [num])
        except Exception:
            pass


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
        # 兜底层号: 超出管理区上限未分配的图层落到 MANAGED_MAX(脚本管理区,
        # 每轮重建)而非第 1 层(用户层)——避免污染用户自有图形(v1.35)
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
                _mark_curve(obj)                    # 所有权标记(清理只删自己的)
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


def work_part_rules(work_part, curves):
    """曲线列表 → 选择意图规则(BaseCurveDumb: 不做额外链接推断)。"""
    return work_part.ScRuleFactory.CreateRuleBaseCurveDumb(list(curves))


def _add_to_section_compat(section, rules, help_pt):
    """AddToSection 跨版本编组通道(NX10/11/12 与 2312 的唯一差异点)。

    根因(实机探针 v2.1 于 NX10=3.3.2 / NX12=3.6.1 验证): NX2312 的自研绑定会把
    Python None 自动转空指针, 而 NX10/12 绑定要求类型化空对象 NXOpen.NXObject.Null,
    裸 None 会抛 "没有过载与这些参数匹配"(TypeError)。__doc__ 证实签名各版一致:
    AddToSection(rules, seed, startConnector, endConnector, helpPoint, featureMode
    [, chainWithinFeature])。rules 用 Python list、helpPoint 用 Point3d 各版皆可
    (对照 ReplaceRules/CreateLine 实测通过), 故仅 seed/两 connector 需换 null 形态。

    策略: 先按 2312 原式(None)调用 —— 现网 2312 路径逐字节不变、零回归; 仅当抛
    异常(旧版)才用 NXObject.Null 重试。重试的异常不吞, 让真实几何错误正常上抛。"""
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
    """ScRuleFactory.CreateRuleOptions 仅 NX2312 等新版本有; NX10/12 该属性不存在
    (实机探针 v2.1: AttributeError), 且旧版 CreateRuleFaceDumb/CreateRuleOuterEdges
    OfFaces 只有"不收 ruleOptions"的单参重载(__doc__ 证实)。取不到返回 None, 调用方
    据此走无 opts 通道 —— 2312 仍传 opts(现网零回归), 旧版自动降级。"""
    try:
        opts = work_part.ScRuleFactory.CreateRuleOptions()
    except Exception:
        return None
    try:
        opts.SetSelectedFromInactive(False)
    except Exception:
        pass
    return opts


def _set_expr(expr, value_str):
    """跨版本写 NXOpen.Expression 公式。

    NX2312 的 Expression 有 SetFormula(str)；NX10/12 绑定无该方法(实机端到端报
    'NXOpen.Expression' object has no attribute 'SetFormula')，改用 .RightHandSide
    =str(与本文件 Limits 各处同款, 旧版可用)。先试 SetFormula 保证 2312 零回归。"""
    try:
        expr.SetFormula(value_str)
    except Exception:
        expr.RightHandSide = value_str


def extrude_curves(work_part, curves, start, end, name, bool_op=None, help_pt=None,
                   offset=None, draft=None):
    """拉伸一组封闭环曲线: start/end 为绝对 Z 距离。

    bool_op: None=普通创建; ("subtract"/"unite", 目标体)=拉伸时布尔。
    offset: (start, end) 单侧壁偏置(如 (0,5)=壁厚5, 同期刊); draft: 拔模角(度)。
    """
    import NXOpen as nx
    import NXOpen.Features             # 子模块必须显式 import, 否则包属性不存在
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
            except Exception:          # 某些曲线类型该属性取值会抛错
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
        registry.add(feat)
        return feat
    finally:
        try:
            bldr.Destroy()
        except Exception:
            pass


def modeling_ents(layers, code):
    """建模用 DXF 实体: CX 并入 CXK 的曲线一起找闭环。

    (用户定案: CXK 层唯一用途=接线盒定位线; 2D 新规则下 CX 单独不成环,
    CX+CXK 才恢复过去的闭环。)返回列表, 与 nx_curves_by_ent 同序拼接。
    """
    ents = list(layers.get(code) or [])
    if code == "CX" and (layers.get("CXK") or []):
        ents += list(layers["CXK"])
    return ents


def build_layer(session, work_part, code, zh, role, layers, nx_curves_by_ent,
                params, flb_regions, log, stats):
    """单图层建模: 环组织 → 拉伸 → 布尔。

    FLB(target) 各轮廓独立成体并登记 (体, 包围盒) — NX 的拉伸时"合并"对不相交
    轮廓只会生成独立体, 因此不做合并; subtract 层按工具位置从包围盒匹配目标体。
    返回 (bodies, regions): regions 仅 target 层非空, 供 subtract 层匹配。
    """
    import NXOpen as nx

    start, end = params[code]
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
        """按轮廓中心点在登记的 FLB 区域里找包含它的体。"""
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        for body, b in flb_regions:
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                return body
        return None

    nx_curves = modeling_ents(nx_curves_by_ent, code)   # 与 ents 同序拼接
    bodies, regions = [], []
    fi = 0

    def chain_curves(item):
        """环条目 → NX 曲线对象列表; 含创建失败(None)则返回 None。"""
        if item.get("chain") is not None:
            idxs = [i for (i, _r) in item["chain"]]
        else:
            idxs = [ents.index(item["circle"])]
        cs = [nx_curves[i] for i in idxs]
        if any(c is None for c in cs):
            log("【%s】轮廓含创建失败的曲线, 该轮廓跳过。" % code)
            return None
        return cs

    def chain_help(item):
        """环上一点(DXF 几何直接算, 作 Section helpPoint)。"""
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

        # 外环的拉伸时布尔: subtract 层从位置匹配的 FLB 体减去, 其余普通创建
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

        # 孔(同层嵌套内环)处理
        for k, hole in enumerate(holes):
            hc = chain_curves(hole)
            if hc is None:
                continue
            if op is not None:
                # 外环已从 FLB 减去整盘, 内环(芯)并回被减的 FLB 体 → 净效果为环形腔
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


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


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
            pass                       # 已被布尔消费/失效的体, 跳过
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
        if bld is not None:          # Commit 抛异常也要销毁 builder(v1.35)
            try:
                bld.Destroy()
            except Exception:
                pass
    registry.clear()                  # 特征已无, 登记表清空
    log("【移除参数】完成: %d 个实体已去参数化(重跑按标记清理)。" % len(ok_bodies))
    return len(ok_bodies)
