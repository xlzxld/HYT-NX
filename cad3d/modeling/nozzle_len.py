# -*- coding: utf-8 -*-
"""cad3d.modeling.nozzle_len —— 热咀替换时按旧件长度调整新件长度。

口径(2026-09-18 用户定案): 替换热咀族(大水口/点胶口/热咀/nozzle)时, 新件
"顶部到底部"的总长要对齐被换掉的旧件 —— 新件比旧件短就拉长、比旧件长就缩短。
旧件长度 = 该处实例**所有体**的世界 Z 最高与最低之差(不看几个实体, 只看最高
面和最低面)。

做法 = 用户手动做法(见其录制日记 logs/journal.py): 用同步建模「移动面」
(`AdmMoveFace`) 把"顶部往下 NOZZLE_KEEP_HEAD mm"这一段**以下的面**沿世界 Z
平移差值 —— 就地改面, 体不重建、头与身之间不会留缝:

  · 头与身是**分开的体**时, 这些体的面整块都在带以下 → 等价于随动平移;
  · 头与身是**同一个体**时, 只有该体带以下的面(含头底那圈)被移 → 体被拉伸。

**不是**把实体整体搬走(v2.13 的做法): 那样头和身之间会断开, 几何对不上。
选面错不了: 判据是"整块面都在带以下"(金字塔底面/端面), 侧面只要伸进头部带
就不动, 与日记里手选的面一致。
"""

from cad3d.core.constants import (
    NOZZLE_FAMILIES,
    NOZZLE_KEEP_HEAD,
    NOZZLE_LEN_TOL,
)

_EQUAL_NOTE = "新旧等长"

# 移面的"那一带"半宽(2026-09-18 用户定案): **定位点上下各 15mm, 共 30mm** ——
# 要移的面就落在这个带里(录制日记里他移的是 Z=−15/0/+13/+6.5, 全在带内)。
_BAND_HALF = 15.0
# 判定"水平面"(朝上/朝下)的 Z 跨度上限: 面围盒的 zmax−zmin 小于它就算
_FLAT_TOL = 0.1

# 移面对齐的收敛控制(2026-09-18 加): 移完一次先复测, 还有残差就再移 —— NX 如何
# 延伸相邻面、个别面没跟上, 都可能让一次移面差那么一点点。迭代几轮收到 _LEN_TOL
# 以内, 治用户反馈的"移面之后长度总有一些差距"。
_MAX_ROUNDS = 3
_LEN_TOL = 0.05


def is_nozzle(fname, families=None):
    """(纯逻辑) 文件名含热咀族任一关键词 → True。族表默认取 config。"""
    fams = NOZZLE_FAMILIES if families is None else families
    low = str(fname or "").lower()
    return any(str(k).lower() in low for k in (fams or []))


def plan_shift(old_len, bboxes, axis_sign, keep_head=None, tol=None, span=None,
               fix_z=None):
    """(纯逻辑) 旧件长度 + 新件各体世界包围盒 + 头端朝向 → 移面量与分界高度。

    axis_sign: +1 = 头在顶端(+Z 插入), -1 = 头在底端(-Z 翻转插入)。
    span: (top, bot) —— 按 plane_span 量出来的"主平面口径"顶/底(用户 2026-09-18
      定案: 小凸起不算)。传了就用它算新件长度与分界高度; 不传就从 bboxes 取
      (旧行为)。**旧件长度必须是同一个口径量出来的**, 否则两边口径不同, 白对齐。
    fix_z: **移面必须不动**的那个高度 = **放置点的 Z**(也就是件上"定位点"——
      那个 Z=0 面的圆心 —— 所落的高度)。用户 2026-09-18 定案: 定位点是件上某个
      面的圆心, **它必须永远与放置点重合**; 一旦被移面带走, 件就"Z 轴偏移"。
      所以分界高度取"头部带"与它之间**更严**的那个(头在顶时取更低的):
      cut = min(top - keep_head, fix_z)。不传则只用头部带(旧行为)。
    返回 (shift, cut, note):
      shift = None → 不用/不能调(note 说原因);
      否则 shift = 沿世界 Z 要移动的量(mm), cut = 头部带的分界高度 ——
      调用方把"整块都在 cut 以下(axis_sign<0 时以上)的面"移 shift。
    拉伸方向: 头在顶端时把下半段往下移就变长(shift<0), 头在底端时反之。
    """
    keep_head = NOZZLE_KEEP_HEAD if keep_head is None else float(keep_head)
    tol = NOZZLE_LEN_TOL if tol is None else float(tol)
    if old_len is None:
        return None, None, "旧件长度没找到, 不调长度"
    try:
        old_len = float(old_len)
    except (TypeError, ValueError):
        return None, None, "旧件长度读不出来, 不调长度"
    if old_len <= 0:
        return None, None, "旧件长度不是正数, 不调长度"
    vals = []
    for b in (bboxes or []):
        if not b or len(b) < 6:
            return None, None, "新件有体的包围盒读不到, 不调长度"
        vals.append((float(b[0]), float(b[1]), float(b[2]),
                     float(b[3]), float(b[4]), float(b[5])))
    if not vals:
        return None, None, "新件没有实体, 不调长度"
    if span is not None and span[0] is not None and span[1] is not None:
        top, bot = float(span[0]), float(span[1])
    else:
        top = max(b[5] for b in vals)
        bot = min(b[2] for b in vals)
    new_len = top - bot
    shift = (1.0 if axis_sign >= 0 else -1.0) * (new_len - old_len)
    cut = (top - keep_head) if axis_sign >= 0 else (bot + keep_head)
    if fix_z is not None:
        # 定位面(放置点高度)绝不能进移面范围 —— 取更严的那个分界
        try:
            _fz = float(fix_z)
            cut = min(cut, _fz) if axis_sign >= 0 else max(cut, _fz)
        except (TypeError, ValueError):
            pass
    if abs(shift) <= tol:
        # 带上实测长度: 只报"免调"看不到数字, 量得对不对没法核对
        return None, None, "%s(都是 %.4g), 免调" % (_EQUAL_NOTE, new_len)
    return shift, cut, ""


def pick_faces(face_boxes, center_z, half=None, flat_only=True, tol=0.01):
    """(纯逻辑) 挑出要移的面 —— **定位点上下 half 那一带里的水平面**。

    center_z = **定位点所在高度**(= 放置点 Z, 件上那个 Z=0 面放置后就在这儿)。
    只选 Z 落在这个带里的**水平面**(朝上/朝下): 移它们就等于"把件在定位点这一段
    挪一挪", 拉长/缩短都从这一段出 —— 带外的(顶尖、身部)一律不动。

    ⭐ 用户 2026-09-18 定案 + 录制日记佐证: 他移的面 Z = −15 / 0 / +13 / +6.5,
    全落在定位点 ±15 这一带(共 30mm)里; 头部其余部分与身部都没动。
    "移动的就是头部, 下面不动" —— 带就是从这里来的。

    侧面(圆柱外圆等)不选 —— 沿轴向平移侧壁没有几何意义(见早前注释)。
    flat_only=False 时连侧面一起要(极端形状保底)。
    """
    half = _BAND_HALF if half is None else float(half)
    out = []
    for i, b in enumerate(face_boxes or []):
        if not b or len(b) < 6:
            continue
        z_lo, z_hi = float(b[2]), float(b[5])
        if flat_only and (z_hi - z_lo) > _FLAT_TOL:
            continue
        if abs((z_lo + z_hi) / 2.0 - float(center_z)) <= half + tol:
            out.append(i)
    return out


def next_step(old_len, cur_len, axis_sign=None, tol=None):
    """(纯逻辑) 复测出来的残差 → 这一轮该沿世界 Z 移多少; 已经够准就返回 0。

    ⭐ 用用户 2026-09-18 的例子校准: 他移 **Δ = −20 时总长**短**了 20** ⇒
    **总长变化 = +Δ**(移多少就长多少, 负就缩短)。
    ⇒ 想让件从 cur_len 变成 old_len, 该移 **Δ = old_len − cur_len**。
    (⚠️ 曾写成相反符号, 实机上就是"越移越远": 124.7 要缩到 118, 结果变 131.6)
    axis_sign 只作签名兼容(新口径下不再需要区分头端朝向)。
    """
    tol = _LEN_TOL if tol is None else float(tol)
    try:
        _d = float(old_len) - float(cur_len)
    except (TypeError, ValueError):
        return 0.0
    return _d if abs(_d) > tol else 0.0


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


def _move_bodies_point_to_point(work_part, session, bodies, from_pt, to_pt, log):
    """把一组体整体平移, 使 from_pt 落到 to_pt —— 用户录制日记的做法。

    日记(`logs/journal-1.py`)用的是「移动对象 + **点对点**」:
      `BaseFeatures.CreateMoveObjectBuilder` → `TransformMotion.Option=PointToPoint`
      → 各建一个临时点当 `FromPoint`/`ToPoint` → `ObjectToMoveObject.Add(体)` → `Commit`。

    用途: **移面之后件上"定位点"被带走了, 用它把定位点搬回放置点** ——
    "件的定位点与放置点永远重合"(用户 2026-09-18 定案)。
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
            log("【定位补偿】本 NX 建不出移动对象(%s), 这处不补偿。" % ex)
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
            log("【定位补偿】点对点设置不上(%s), 这处不补偿。" % ex)
            return False
        bld.ObjectToMoveObject.Add(list(bodies))
        # ⚠️ 别照搬"移面"的 OnApplyPre: MoveObjectBuilder 没有这个方法
        # (实机报过 'no attribute OnApplyPre', 日记里也只有 Commit)。有的版本
        # 需要就调一下, 没有直接跳过。
        try:
            bld.OnApplyPre()
        except AttributeError:
            pass
        bld.Commit()
        return True
    except Exception as ex:
        log("【定位补偿】移动对象失败(%s), 这件位置可能偏。" % ex)
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
    防止 NX 把不在带以下的侧面顺手选进来(与日记一致)。
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
            log("【长度对齐】移动面提交失败(%s), 这处保持原长。" % ex)
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
    (移面就地改, **体列表原样返回**); 出错/不可用则本处保持原长不动。
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
        bboxes = [_body_bbox(uf, t) for t in tools]
        # 长度按"主平面口径"量(用户 2026-09-18 定案): 顶 = 朝上的平面里最高的,
        # 底 = 朝下的平面里最低的 —— 顶上的小凸起是曲面, 天然落不进"平面"
        rows = read_face_rows(uf, tools)
        top0, bot0, how = plane_span(rows, _union_bbox(bboxes))
        span0 = (top0, bot0) if top0 is not None and bot0 is not None else None
        new_len0 = (top0 - bot0) if span0 else _len_of(bboxes)
        axis_sign = -1.0 if rule.get("dir") == "-Z" else 1.0
        # fix_z = 放置点的高度(anch[2]): 件上"定位点"(那个 Z=0 面的圆心)必须永远
        # 落在放置点上 —— 它的高度就是放置点高度, 绝不能进移面范围, 否则一拉长
        # 定位点就被带走、件就 Z 轴偏移(用户 2026-09-18 定案)
        try:
            _fix_z = float(anch[2])
        except (TypeError, ValueError, IndexError):
            _fix_z = None
        shift, _cut, note = plan_shift(old_len, bboxes, axis_sign, span=span0,
                                       fix_z=_fix_z)
        if shift is None:
            log("【长度对齐】%s 第 %d 处: %s。" % (fname, idx, note))
            if not note.startswith(_EQUAL_NOTE):
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        # 逐根打"这一根是怎么量出来的": 口径 + 顶底 + 合出来的总长。每根热咀
        # 长度都可能不同, 对不上时先看这行就知道是量错了还是几何不对
        log("【长度对齐】%s 第 %d 处: 新件 %d 个体, 按%s量 Z %.4g~%.4g → 长 %.4g"
            % (fname, idx, len(tools), how, bot0, top0, new_len0))

        # 移面 → 复测 → 还有残差就再移(最多 _MAX_ROUNDS 轮)。一轮移不干净的原因
        # 不少(NX 延伸相邻面的行为、个别面没跟上), 迭代几轮就收敛了。
        moved = 0
        cur = new_len0
        for _r in range(_MAX_ROUNDS):
            if cur is None:
                break
            step = next_step(old_len, cur, axis_sign)
            if step == 0.0:
                break
            rows = read_face_rows(uf, tools)     # 每轮重取: 移面后几何与面都变了
            # 移的面 = **定位点(_fix_z)上下 ±15 那一带**里的水平面(用户定案)
            idxs = pick_faces([r[0] for r in rows], _fix_z)
            if not idxs:
                # 极端形状(这一带里一个水平面都没有) → 退回宽口径, 至少能动
                idxs = pick_faces([r[0] for r in rows], _fix_z, flat_only=False)
            faces = [rows[i][3] for i in idxs]
            if not faces:
                log("【长度对齐】%s 第 %d 处: 定位点±%.4g 那一带里没有可移的面"
                    "(旧件长 %.4g, 新件长 %.4g), 这处保持原长。"
                    % (fname, idx, _BAND_HALF, old_len, cur))
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
                return tools
            if not _move_faces_z(work_part, session, faces, step, log):
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
                return tools
            moved += len(faces)
            _bb2 = [_body_bbox(uf, t) for t in tools]
            _t2, _b2, _h2 = plane_span(read_face_rows(uf, tools),
                                       _union_bbox(_bb2))
            cur = (_t2 - _b2) if (_t2 is not None and _b2 is not None) \
                else _len_of(_bb2)

        if cur is None or abs(cur - old_len) > _LEN_TOL:
            log("【长度对齐】%s 第 %d 处: 移面后长 %.4g ≠ 旧件 %.4g(还差 %.4g), "
                "已留下改动供你核对(体没换, 只动了几块面)。"
                % (fname, idx, cur if cur is not None else float("nan"),
                   old_len, (cur - old_len) if cur is not None else float("nan")))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools

        # ⭐ 定位点补偿(用户 2026-09-18 定案): 移面把件上"定位点"(那个 Z=0 面的
        # 圆心)带走了, 用「移动对象 + 点对点」把它搬回**放置点** —— 让"动态的
        # 定位点"永远与"绝对的放置点"重合。换算关系也用他给的:
        #   换算关系(用他给的例子校准): **总长变化 = +Δ**(移多少就长多少) ⇒
        #   Δ = 旧件长 − 新件原长; 移面后定位点在世界里的位置 = 放置点 + (0,0,Δ)。
        real_delta = old_len - new_len0
        if _fix_z is not None and abs(real_delta) > 1e-9:
            _from = (float(anch[0]), float(anch[1]), float(_fix_z) + real_delta)
            _to = (float(anch[0]), float(anch[1]), float(_fix_z))
            if _move_bodies_point_to_point(work_part, session, tools,
                                           _from, _to, log):
                log("【定位补偿】%s 第 %d 处: 定位点 (%.4g,%.4g,%.4g) → 放置点 "
                    "(%.4g,%.4g,%.4g), 件已整体平移回位。"
                    % (fname, idx, _from[0], _from[1], _from[2],
                       _to[0], _to[1], _to[2]))

        adj_stats["adj"] = adj_stats.get("adj", 0) + 1
        log("【长度对齐】%s 第 %d 处: 旧件长 %.4g, 新件原长 %.4g(新件 %d 个体)"
            " → 净拉长 %.4g mm 对齐(移的是定位点±%.4g 那一带, 动了 %d 块面)。"
            % (fname, idx, old_len, new_len0, len(tools), old_len - new_len0,
               _BAND_HALF, moved))
        return tools

    return hook


def _len_of(bboxes):
    """[(包围盒6)] → 世界 Z 总高; 缺盒/空 → None。"""
    vals = [b for b in (bboxes or []) if b and len(b) >= 6]
    if not vals:
        return None
    return max(float(b[5]) for b in vals) - min(float(b[2]) for b in vals)
