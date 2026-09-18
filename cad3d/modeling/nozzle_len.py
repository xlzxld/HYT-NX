# -*- coding: utf-8 -*-
"""cad3d.modeling.nozzle_len —— 热咀替换时按旧件长度调整新件长度。

口径(2026-09-18 用户定案): 替换热咀族(大水口/点胶口/热咀/nozzle)时, 新件
"顶部到底部"的总长要对齐被换掉的旧件 —— 新件比旧件短就拉长、比旧件长就缩短。
旧件长度 = 该处实例所有体的"主平面口径"顶减底(朝上平面里最高的减朝下平面里
最低的; 顶上的曲面小凸起天然不算, 点胶口-18 实测 95.9673 与用户手量一致)。

做法(v3.4, 用户 2026-09-19 定案):
  1. 新件**先原位摆正**(place_std_parts 按锚点放置, 定位点=旧件锚点);
  2. **移面选择范围 = 热咀底面到顶面再整体上移 NOZZLE_BAND_UP(40mm)** ——
     一根咀底/顶面 z 是 0/100 的咀, 选择范围就是 [40,140]: 咀尖底部 40mm
     固定不动, **范围内被选中的一切面都要移动**; **所有被选中实体的带内面
     合成一份、一次「移动面」一起移**(有多少实体被选中, 就移多少实体中被
     选中的面, 不能只移一个实体的); **一步移到位**(v3.5: 之前拆小步是
     因为选择范围窄容易扯脱, 范围扩到 [底+40,顶+40] 后实测不必再拆);
  3. 移多移少、往哪边移**现场校准**, 不猜符号: 先探一小步(−2mm)复测, 量出
     "每移 1mm 总长变多少"(符号各件不同), 再按斜率补齐, 复测、不齐再补
     (有轮数上限);
  4. **定位点回位(2026-09-19 定案)**: 若定位点落在选择范围内, 移面会把它
     带走 cum, 件的定位点就落在 放置点+cum 上了 —— 照日记的「移动对象-
     点对点」把**整个新件**平移 −cum, 让定位点与放置点重新重合(journal-1:
     From (0,0,−20) → To 锚点)。整件平移不改长度, 长度照旧对齐。回位前先
     **去掉建模参数**(日记顺序: 移面→去参→移动对象; 提升体是 Wave 链接,
     NX 不许整体移动)。定位点不在选择范围内(咀底部 40mm 以内)时它根本
     不会被带走, 无需回位。

失败兜底: 移面做不成/收敛不了时, 位置也不会偏(没移成就没有 cum, 或回位
把已移的搬回来), 日志写明长度差多少 —— 不出现"为对长度把位置搭进去"。
"""

from cad3d.core.constants import (
    NOZZLE_BAND_UP,
    NOZZLE_FAMILIES,
)

# 方向校准探步(mm): 先移这一小步, 复测出"每移 1mm 总长变多少"
_PROBE_STEP = 2.0
# 斜率下限: |斜率| 低于它 = 移了面长度也不跟变(范围内面不控制总长), 放弃
_SLOPE_MIN = 0.2
# 补差主循环轮数(每轮: 按斜率一步移到位 → 复测; 留几轮是给斜率重校兜底)
_MAX_STEPS = 6
# 长度对齐判定容差(mm)
_LEN_TOL = 0.05


def is_nozzle(fname, families=None):
    """(纯逻辑) 文件名含热咀族任一关键词 → True。族表默认取 config。"""
    fams = NOZZLE_FAMILIES if families is None else families
    low = str(fname or "").lower()
    return any(str(k).lower() in low for k in (fams or []))


def pick_faces(face_boxes, z_lo, z_hi, tol=0.01):
    """(纯逻辑) 挑出要移的面 —— **选择范围内的所有面, 一切面都要**。

    范围 = 热咀底面到顶面再整体上移 NOZZLE_BAND_UP(用户 2026-09-19 定案):
    一根咀底/顶面 z 是 0/100 的咀, 选择范围就是 [40,140] —— 咀尖底部 40mm
    固定不动(不在范围内), 范围内的**一切面**(平面/侧面/曲面都要)都移。
    z_lo/z_hi 由调用方按 [底+40, 顶+40] 传入; 按面围盒**中心**的 Z 判定。
    """
    out = []
    for i, b in enumerate(face_boxes or []):
        if not b or len(b) < 6:
            continue
        zc = (float(b[2]) + float(b[5])) / 2.0
        if (float(z_lo) - tol) <= zc <= (float(z_hi) + tol):
            out.append(i)
    return out


def calib_slope(len0, len1, move_z):
    """(纯逻辑) 探步校准: 移 move_z 后总长从 len0 变 len1 → 每移 1mm 长度变多少。

    符号各件不同(带内含不含咀尖), 所以必须探, 不能猜 —— 用户两份日记里
    就有相反的例子。零步/读不到 → 0.0(调用方视为"移面带不动长度")。
    """
    try:
        dz = float(move_z)
        a, b = float(len0), float(len1)
    except (TypeError, ValueError):
        return 0.0
    if abs(dz) < 1e-9:
        return 0.0
    return (b - a) / dz


def step_for(old_len, cur, slope, tol=None):
    """(纯逻辑) 斜率已知时, 把总长从 cur 补到 old_len 该移的量(带符号)。

    已够准/斜率为 0/读不到 → 0.0(调用方停止迭代)。
    """
    tol = _LEN_TOL if tol is None else float(tol)
    try:
        s = float(slope)
    except (TypeError, ValueError):
        return 0.0
    if abs(s) < 1e-9:
        return 0.0
    try:
        remaining = float(old_len) - float(cur)
    except (TypeError, ValueError):
        return 0.0
    if abs(remaining) <= tol:
        return 0.0
    return remaining / s


def nearest_anchor_len(anchor, old_lens, tol=0.05):
    """(纯逻辑) 在 [(锚点, 旧件长度)] 里找与 anchor 重合(容差内)的长度; 无 → None。"""
    try:
        ax, ay, az = float(anchor[0]), float(anchor[1]), float(anchor[2])
    except (TypeError, ValueError, IndexError):
        return None
    for a, ln in (old_lens or []):
        try:
            if (abs(ax - float(a[0])) <= tol and abs(ay - float(a[1])) <= tol
                    and abs(az - float(a[2])) <= tol):
                return ln
        except (TypeError, ValueError, IndexError):
            continue
    return None


def plane_span(rows, bbox=None):
    """(纯逻辑) 按**主平面口径**量顶/底 —— 用户 2026-09-18 定案。

      top = 法向朝上(+Z)的**平面**里 z 最高的那个;
      bot = 法向朝下(-Z)的**平面**里 z 最低的那个。

    为什么不用纯包围盒: 有的件顶上带个小凸起 —— 点胶口-18 顶部就有个 0.2043 的
    **曲面**台阶, 包围盒会把它算进去(得 96.1716), 而工程上认的是主体长度
    (95.9673)。凸起是曲面、不是平面, 用"平面"筛就天然排除了。
    实测三个件都吻合: 点胶口-18 → 95.9673 / 点胶口-25 → 124.6575 /
    大水口-25 → 118.0000。

    一侧找不到平面就那一侧退回包围盒(件顶端是锥面/球面时); 都没有就纯包围盒,
    与旧行为一致。返回 (top, bot, how) —— how 是口径说明, 进日志用。

    rows: [(包围盒6, 法向_z, 是否平面, 面对象), ...] 每个面一条(见 read_face_rows)。
    """
    rows = rows or []
    bbox = bbox if (bbox and len(bbox) >= 6) else None
    tops, bots = [], []
    for r in rows:
        try:
            bb, nz, flat = r[0], float(r[1]), bool(r[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not (flat and bb and len(bb) >= 6):
            continue
        if nz > 0.999:
            tops.append(float(bb[5]))
        elif nz < -0.999:
            bots.append(float(bb[2]))
    top = max(tops) if tops else (float(bbox[5]) if bbox else None)
    bot = min(bots) if bots else (float(bbox[2]) if bbox else None)
    if top is None or bot is None:
        return None, None, "量不到"
    if tops and bots:
        how = "主体平面"
    elif tops or bots:
        how = "一侧平面/一侧包围盒"
    else:
        how = "包围盒(件上没有朝上/朝下的平面)"
    return top, bot, how


def read_face_rows(uf, bodies):
    """(NX 薄壳) 一组体的全部面 → [(包围盒6, 法向_z, 是否平面, 面对象), ...]。

    法向_z 取面法向的 Z 分量; 是否平面按 UF 面数据的半径≈0 判(与
    _find_flat_face 同口径)。读不到的面跳过。
    """
    from cad3d.modeling.jrt import _uf_face_data
    out = []
    for b in bodies or []:
        try:
            faces = list(b.GetFaces())
        except Exception:
            continue
        for f in faces:
            try:
                d = _uf_face_data(uf, f)
                bb = d[3]
                if not bb or len(bb) < 6:
                    continue
                out.append((tuple(float(v) for v in bb[:6]),
                            float(d[2][2]), float(d[4]) < 1e-9, f))
            except Exception:
                continue
    return out


def _union_bbox(bboxes):
    """多个包围盒 → 合并的大盒; 全空返回 None。"""
    vals = [b for b in (bboxes or []) if b and len(b) >= 6]
    if not vals:
        return None
    return (min(b[0] for b in vals), min(b[1] for b in vals),
            min(b[2] for b in vals), max(b[3] for b in vals),
            max(b[4] for b in vals), max(b[5] for b in vals))


def _len_of(bboxes):
    """[(包围盒6)] → 世界 Z 总高; 缺盒/空 → None。"""
    vals = [b for b in (bboxes or []) if b and len(b) >= 6]
    if not vals:
        return None
    return max(float(b[5]) for b in vals) - min(float(b[2]) for b in vals)


def _tune_motion(mo, nx):
    """把"移动面"的运动参数全部收敛到**纯 DeltaXyz 平移** —— 照用户录制的日记逐条设。

    日记里这些**全都显式设过**(OrientXpress / AlongCurveAngle 的各选项、各
    Distance/Angle 表达式归零)。**漏设的后果就是实机上的"移完异形"** —— NX 会
    沿用别的运动模式(方向/曲线), 移出来不是纯平移, 几何被拽歪(用户 2026-09-18)。
    跨版本设不上的只跳过; 关键三项(Option / DeltaEnum / DeltaZc)由调用方单独负责。
    """
    gu = nx.GeometricUtilities
    orient = gu.OrientXpressBuilder

    def _set(path, attr, val):
        """按属性路径逐级取(路径取不到就跳过 —— 跨版本有的节点不存在)。"""
        try:
            obj = mo
            for p in path:
                obj = getattr(obj, p)
            if attr == "SetFormula":
                obj.SetFormula(val)
            else:
                setattr(obj, attr, val)
        except Exception:
            pass

    _set(("DistanceAngle", "OrientXpress"), "AxisOption", orient.Axis.Passive)
    _set(("DistanceAngle", "OrientXpress"), "PlaneOption", orient.Plane.Passive)
    _set(("OrientXpress",), "AxisOption", orient.Axis.Passive)
    _set(("OrientXpress",), "PlaneOption", orient.Plane.Passive)
    for path in (("AlongCurveAngle", "AlongCurve", "Expression"),
                 ("DistanceValue",), ("DistanceBetweenPointsDistance",),
                 ("RadialDistance",), ("Angle",),
                 ("DistanceAngle", "Distance"), ("DistanceAngle", "Angle")):
        _set(path, "SetFormula", "0")
    _set(("AlongCurveAngle", "AlongCurve"), "IsPercentUsed", True)


def _deparameterize_bodies(work_part, bodies, log):
    """去掉一组体的建模参数(变成哑体) —— 日记顺序: 移面之后、移动对象之前。

    「移动对象」只对哑体可用 —— 提升体是 Wave 链接, NX 不许整体移动
    (实机报"属于 Wave 链接特征")。只处理传入的这几个体, 不动全局登记表
    (主流水线收尾还会统一去参)。
    """
    bld = None
    try:
        bld = work_part.Features.CreateRemoveParametersBuilder()
        for b in bodies or []:
            try:
                bld.Objects.Add(b)
            except Exception:
                continue
        bld.Commit()
        return True
    except Exception as ex:
        log("【长度对齐】去参数失败(%s), 仍尝试移面(可能不稳)。" % ex)
        return False
    finally:
        if bld is not None:
            try:
                bld.Destroy()
            except Exception:
                pass


def _move_bodies_point_to_point(work_part, session, bodies, from_pt, to_pt, log):
    """把一组体整体平移, 使 from_pt 落到 to_pt —— 日记(logs/journal-1.py)的
    「移动对象 + 点对点」: CreateMoveObjectBuilder → Option=PointToPoint →
    FromPoint/ToPoint → ObjectToMoveObject.Add(体) → Commit。

    用途: **定位点回位**(用户 2026-09-19 定案) —— 移面把带内的面(含定位面)
    带走了 cum, 件的定位点落在 放置点+cum 上; 用它把整个新件平移 −cum, 让
    定位点与放置点重新重合。整件平移不改长度, 长度照旧对齐。
    ⚠️ 只对哑体可用 —— 提升体是 Wave 链接, NX 不许整体移动(实机报过
    "属于 Wave 链接特征"); 调用方必须先 _deparameterize_bodies(日记顺序:
    移面 → 去参 → 移动对象)。
    """
    import NXOpen
    import NXOpen.Features
    import NXOpen.GeometricUtilities

    bld = None
    p_from = p_to = None
    try:
        try:
            bld = work_part.BaseFeatures.CreateMoveObjectBuilder(
                NXOpen.Features.MoveObject.Null)
        except Exception as ex:
            log("【定位点回位】本 NX 建不出移动对象(%s), 定位点没搬回。" % ex)
            return False
        mo = bld.TransformMotion
        _tune_motion(mo, NXOpen)          # 同款: 运动参数不设全 NX 会沿用别的模式
        try:
            mo.DeltaEnum = \
                NXOpen.GeometricUtilities.ModlMotion.Delta.ReferenceAcsWorkPart
            mo.Option = \
                NXOpen.GeometricUtilities.ModlMotion.Options.PointToPoint
            p_from = work_part.Points.CreatePoint(
                NXOpen.Point3d(float(from_pt[0]), float(from_pt[1]),
                               float(from_pt[2])))
            p_to = work_part.Points.CreatePoint(
                NXOpen.Point3d(float(to_pt[0]), float(to_pt[1]),
                               float(to_pt[2])))
            mo.FromPoint = p_from
            mo.ToPoint = p_to
        except Exception as ex:
            log("【定位点回位】点对点设置不上(%s), 定位点没搬回。" % ex)
            return False
        bld.ObjectToMoveObject.Add(list(bodies))
        # ⚠️ 别照搬"移面"的 OnApplyPre: MoveObjectBuilder 没有这个方法
        # (实机报过 'no attribute OnApplyPre', 日记里也只有 Commit)。
        try:
            bld.OnApplyPre()
        except AttributeError:
            pass
        bld.Commit()
        return True
    except Exception as ex:
        log("【定位点回位】移动对象失败(%s), 定位点还差手搬。" % ex)
        return False
    finally:
        for _p in (p_from, p_to):
            # 临时点用完撤参数、去掉视图依赖(日记同款); 只是基准点, 不影响几何
            try:
                if _p is not None:
                    _p.RemoveParameters()
                    _p.RemoveViewDependency()
            except Exception:
                pass
        try:
            if bld is not None:
                bld.Destroy()
        except Exception:
            pass


def _move_faces_z(work_part, session, faces, shift, log):
    """用同步建模「移动面」把给定面沿世界 Z 平移 shift。成功 True。

    API 序列照用户 2026-09-18 录制的日记(logs/journal.py):
      Create*MoveFaceBuilder → Motion=DeltaXyz(世界 Z) → FaceCollector.ReplaceRules
      → OnApplyPre → Commit。
    构造器按名字**探测**(不同版本方法名可能不同), 拿不到就跳过并记日志 ——
    绝不猜 API 名。同时把 Coplanar/Coaxial/Tangent 等"自动找同族面"开关全关掉,
    防止 NX 把带外的侧面顺手选进来(与日记一致)。
    """
    import NXOpen
    import NXOpen.Features
    import NXOpen.GeometricUtilities

    from cad3d.modeling.extrude import _sc_rule_options

    feats = work_part.Features
    maker = None
    maker_name = ""
    for name in sorted(dir(feats)):
        if name.startswith("Create") and "MoveFace" in name:
            maker = getattr(feats, name)
            maker_name = name
            break
    if maker is None:
        log("【长度对齐】本 NX 没有「移动面」接口(Create*MoveFace*), 这处保持原长。")
        return False
    null_tok = None
    for cls_name in ("AdmMoveFace", "MoveFace"):
        cls = getattr(NXOpen.Features, cls_name, None)
        if cls is not None and hasattr(cls, "Null"):
            null_tok = cls.Null
            break
    if null_tok is None:
        null_tok = getattr(NXOpen.Features.Feature, "Null", None)
    if null_tok is None:
        log("【长度对齐】拿不到移动面的空令牌, 这处保持原长。")
        return False
    try:
        bld = maker(null_tok)
    except Exception as ex:
        log("【长度对齐】%s 建不出来(%s), 这处保持原长。" % (maker_name, ex))
        return False
    try:
        try:
            bld.Motion.Option = \
                NXOpen.GeometricUtilities.ModlMotion.Options.DeltaXyz
            bld.Motion.DeltaEnum = \
                NXOpen.GeometricUtilities.ModlMotion.Delta.ReferenceAcsWorkPart
            bld.Motion.DeltaXc.SetFormula("0")
            bld.Motion.DeltaYc.SetFormula("0")
            bld.Motion.DeltaZc.SetFormula("%.6f" % float(shift))
        except Exception as ex:
            log("【长度对齐】本 NX 的移动面没有 DeltaXyz 运动选项(%s), 这处保持原长。"
                % ex)
            return False
        # 其余运动参数照日记全部归零/关掉 —— **不设就会"移完异形"**(实机踩过)
        _tune_motion(bld.Motion, NXOpen)
        for attr, val in (("RelationScope", 1023), ("CloneScope", 511),
                          ("UseFindClone", True), ("UseFindRelated", True),
                          ("UseFaceBrowse", True),
                          ("FindGeneralClone", True),      # 日记里有, 漏了会少延伸
                          ("CoplanarEnabled", False),
                          ("CoplanarAxesEnabled", False),
                          ("CoaxialEnabled", False),
                          ("SameOrbitEnabled", False),
                          ("EqualDiameterEnabled", False),
                          ("TangentEnabled", False),
                          ("SymmetricEnabled", False),
                          ("OffsetEnabled", False),
                          ("RigidBodyFaceEnabled", False)):
            try:
                setattr(bld.FaceToMove, attr, val)
            except Exception:
                continue
        for attr, val in (("HealOption", False), ("PasteOption", True)):
            try:
                setattr(bld, attr, val)
            except Exception:
                continue
        # 清空"虚拟面"收集器(日记里也做了): 留着可能把上次的面一起带进来
        try:
            bld.FaceToMove.VirtualFaceCollector.ReplaceRules([], False)
        except Exception:
            pass
        opts = _sc_rule_options(work_part)
        try:
            if opts is not None:
                try:
                    rule = work_part.ScRuleFactory.CreateRuleFaceDumb(
                        list(faces), opts)
                except TypeError:
                    rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
            else:
                rule = work_part.ScRuleFactory.CreateRuleFaceDumb(list(faces))
        finally:
            if opts is not None:
                try:
                    opts.Dispose()
                except Exception:
                    pass
        bld.FaceToMove.FaceCollector.ReplaceRules([rule], False)
        bld.OnApplyPre()
        mark = None
        try:
            mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible,
                                       "CAD3D 热咀长度对齐")
        except Exception:
            mark = None
        try:
            bld.Commit()
        except Exception as ex:
            log("【长度对齐】移动面提交失败(%s)。" % ex)
            if mark is not None:
                try:
                    session.UndoToMark(mark, None)
                except Exception:
                    pass
            return False
        finally:
            if mark is not None:
                try:
                    session.DeleteUndoMark(mark, None)
                except Exception:
                    pass
        return True
    finally:
        try:
            bld.Destroy()
        except Exception:
            pass


def make_nozzle_hook(session, work_part, old_lens, log, adj_stats=None):
    """造一个 place_std_parts 的 placed_hook: 放好的热咀按旧件长度移面对齐。

    old_lens: [(锚点(x,y,z,..), 旧件实例长度), ...] —— 替换入口按旧件体
    分组算好传入; adj_stats: 可变 dict, 回填 adj/skip 计数供报告。
    hook 签名 (fname, 序号, 锚点, 规则, 体列表, 待删组件列表) → 新体列表
    (移面就地改 + 定位点回位, 体列表原样返回)。
    流程 = 用户 2026-09-19 定案: 摆正(放置时已做) → 带内移面(所有被选实体
    的面一起移, 一步移到位, 方向探步校准) → 去参 → 整件点对点平移回位,
    让定位点与放置点重新重合。
    """
    try:
        import NXOpen.UF
        uf = NXOpen.UF.UFSession.GetUFSession()
        from cad3d.modeling.mold_cut import _body_bbox
    except Exception as ex:
        uf = None
        _body_bbox = None
        log("【长度对齐】拿不到包围盒接口, 热咀长度对齐全部跳过(%s)。" % ex)

    if adj_stats is None:
        adj_stats = {}

    def hook(fname, idx, anch, rule, tools, pending_comps):
        if uf is None or _body_bbox is None or not tools:
            return tools
        if not is_nozzle(fname):
            return tools
        old_len = nearest_anchor_len(anch, old_lens)
        if old_len is None:
            log("【长度对齐】%s 第 %d 处: 这根的旧件长度没量到, 保持新件原长"
                "(位置不受影响)。" % (fname, idx))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        try:
            # 定位点 = 放置点(锚点): 移面带的中心、回位的目标点都用它
            _cx, _cy, _fix_z = float(anch[0]), float(anch[1]), float(anch[2])
        except (TypeError, ValueError, IndexError):
            log("【长度对齐】%s 第 %d 处: 锚点读不出来, 不调。"
                % (fname, idx))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools

        def _measure():
            bbs = [_body_bbox(uf, t) for t in tools]
            t, b, how = plane_span(read_face_rows(uf, tools), _union_bbox(bbs))
            if t is None or b is None:
                return _len_of(bbs), how, None, None
            return (t - b), how, t, b

        def _band_faces():
            """按"范围=[当前底+40, 当前顶+40]"挑出**一切被选中的面**。

            所有体的面合成一份、一次「移动面」一起移(用户定案: 有多少实体
            被选中, 就移多少实体中被选中的面, 不能只移一个实体的)。
            每轮按当前跨度重算: 咀尖底部 40mm 固定不动 → 下缘不变;
            顶端随件走 → 上缘跟着抬, 已移的面仍在范围内。
            (这里直接调 plane_span 拿跨度 —— _measure() 返回 4 元组, 曾被
            按 3 个解包, 实机探步第一步就 "too many values to unpack" 整批
            回滚, 2026-09-19。)
            """
            bbs = [_body_bbox(uf, t) for t in tools]
            t2, b2, _h2 = plane_span(read_face_rows(uf, tools),
                                     _union_bbox(bbs))
            if b2 is None or t2 is None:
                return []
            rows = read_face_rows(uf, tools)
            idxs = pick_faces([r[0] for r in rows],
                              b2 + NOZZLE_BAND_UP, t2 + NOZZLE_BAND_UP)
            return [rows[i][3] for i in idxs]

        def _move(amount):
            """把范围内一切被选中的面一起沿 Z 移 amount; 返回实际移了的量。"""
            fs = _band_faces()
            if not fs:
                log("【长度对齐】%s 第 %d 处: 选择范围(底+%.4g 以上)里没有可移"
                    "的面。" % (fname, idx, NOZZLE_BAND_UP))
                return 0.0
            if _move_faces_z(work_part, session, fs, amount, log):
                return amount
            return 0.0

        def _restore(cum):
            """定位点回位(用户 2026-09-19 定案): 整件平移 −cum, 让定位点
            (被移面带走了 cum)重新落到放置点上 —— 日记「移动对象-点对点」。
            先去参(提升体是 Wave 链接, 不许整体移动; 日记顺序:
            移面 → 去参 → 移动对象)。整件平移不改长度。"""
            if abs(cum) <= 1e-9:
                return True
            _deparameterize_bodies(work_part, tools, log)
            ok = _move_bodies_point_to_point(
                work_part, session, tools,
                (_cx, _cy, _fix_z + cum), (_cx, _cy, _fix_z), log)
            if ok:
                log("【定位点回位】%s 第 %d 处: 整件平移 %.4g mm, 定位点回到"
                    "放置点(%.3f, %.3f, %.3f)。"
                    % (fname, idx, -cum, _cx, _cy, _fix_z))
            return ok

        # ① 量当前长度与跨度; 选择范围 = [底+40, 顶+40](用户定案)
        cur, how, t0, b0 = _measure()
        if cur is None or b0 is None or t0 is None:
            log("【长度对齐】%s 第 %d 处: 新件长度量不到, 保持原样(位置正确)。"
                % (fname, idx))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        datum_moves = _fix_z >= (b0 + NOZZLE_BAND_UP - 0.05)
        log("【长度对齐】%s 第 %d 处: 新件 %d 个体, 按%s量 Z %.4g~%.4g → 长 %.4g"
            " (旧件 %.4g); 移面选择范围 Z %.4g~%.4g(底+%.4g~顶+%.4g), "
            "定位点(%s)在范围内%s。"
            % (fname, idx, len(tools), how, b0, t0, cur, old_len,
               b0 + NOZZLE_BAND_UP, t0 + NOZZLE_BAND_UP,
               NOZZLE_BAND_UP, NOZZLE_BAND_UP, _fix_z,
               "→ 会被带走, 移完回位" if datum_moves else "→ 固定端, 不会动"))
        if abs(old_len - cur) <= _LEN_TOL:
            log("【长度对齐】%s 第 %d 处: 新旧等长(都是 %.4g), 免调。"
                % (fname, idx, cur))
            return tools

        # ② 探向: 先移一小步, 量出"每移 1mm 总长变多少"(符号各件不同, 不猜)
        cum = 0.0                    # 范围内面被带走的累计量(定位点在带内=回位量)
        applied = _move(-_PROBE_STEP)
        if applied == 0.0:
            log("【长度对齐】%s 第 %d 处: 探步就移不动, 保持新件原长 %.4g"
                "(位置正确, 与旧件差 %.4g)。"
                % (fname, idx, cur, old_len - cur))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        cum += applied
        prev, cur = cur, _measure()[0]
        slope = calib_slope(prev, cur, applied)
        if cur is None or abs(slope) < _SLOPE_MIN:
            log("【长度对齐】%s 第 %d 处: 移了面总长没跟变(范围内面不控制总长), "
                "保持现状(长度 %.4g, 旧件 %.4g)。" % (fname, idx, cur, old_len))
            if datum_moves:
                _restore(cum)
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools

        # ③ 按斜率**一步移到位**(用户 2026-09-19 定案: 之前失败是选择范围窄,
        # 现在范围大了不用拆小步), 复测, 不齐再补; 每轮用实测重校斜率
        for _r in range(_MAX_STEPS):
            step = step_for(old_len, cur, slope)
            if step == 0.0:
                break
            applied = _move(step)
            if applied == 0.0:
                log("【长度对齐】%s 第 %d 处: 移面提交失败, 保持现状"
                    "(长 %.4g, 旧件 %.4g, 还差 %.4g)。"
                    % (fname, idx, cur, old_len, old_len - cur))
                break
            cum += applied
            prev, cur = cur, _measure()[0]
            if cur is None:
                break
            _s2 = calib_slope(prev, cur, applied)
            if abs(_s2) >= _SLOPE_MIN:
                slope = _s2

        # ④ 定位点回位(只有定位点在范围内、被移面带走时才需要)
        restored = True
        if datum_moves:
            restored = _restore(cum)

        # ⑤ 结论
        if cur is not None and abs(old_len - cur) <= _LEN_TOL:
            if restored:
                adj_stats["adj"] = adj_stats.get("adj", 0) + 1
                log("【长度对齐】%s 第 %d 处: 对齐完成 —— 总长 %.4g = 旧件 %.4g,"
                    " 定位点在放置点上(范围内共移 %.4g mm, 方向斜率 %.4g)。"
                    % (fname, idx, cur, old_len, cum, slope))
            else:
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
                log("【长度对齐】%s 第 %d 处: 长度已对齐(%.4g)但定位点没搬回, "
                    "整件还差 %.4g mm, 请手动移动。"
                    % (fname, idx, cur, -cum))
        else:
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            log("【长度对齐】%s 第 %d 处: 没收敛 —— 现在 %.4g, 旧件 %.4g, "
                "还差 %.4g。%s, 长度请按日志数字手动收尾(移动面选 底+%.4g"
                "~顶+%.4g 范围内的面)。"
                % (fname, idx, cur if cur is not None else float("nan"),
                   old_len,
                   (old_len - cur) if cur is not None else float("nan"),
                   "位置已回正(定位点在放置点上)" if restored
                   else "定位点没搬回, 整件差 %.4g mm" % (-cum),
                   NOZZLE_BAND_UP, NOZZLE_BAND_UP))
        return tools

    return hook
