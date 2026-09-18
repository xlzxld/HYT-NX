# -*- coding: utf-8 -*-
"""cad3d.modeling.nozzle_len —— 热咀替换时按旧件长度调整新件长度。

口径(2026-09-18 用户定案): 替换热咀族(大水口/点胶口/热咀/nozzle)时, 新件
"顶部到底部"的总长要对齐被换掉的旧件 —— 新件比旧件短就拉长、比旧件长就缩短。
旧件长度 = 该处实例所有体的"主平面口径"顶减底(朝上平面里最高的减朝下平面里
最低的; 顶上的曲面小凸起天然不算, 点胶口-18 实测 95.9673 与用户手量一致)。

做法(v3.3, 完全照用户录制的日记 logs/journal.py / journal-1.py):
  1. 新件**先原位摆正**(place_std_parts 按锚点放置, 定位点=旧件锚点) ——
     位置从头就是对的, 后面移面成不成都不影响位置;
  2. **去掉建模参数**(RemoveParameters, 变成哑体) —— 两份日记里移面的对象
     都是 UNPARAMETERIZED 哑体; 之前实机"大面积移面失败(面不再与先前的
     邻近对象相交)"就发生在还没去参的 Wave 链接提升体上;
  3. 用同步建模「移动面」(AdmMoveFace, 运动参数照日记逐条设全)在**定位点
     上下各 15mm(共 NOZZLE_KEEP_HEAD=30)的带内**移面, 把总长补到旧件长度;
  4. 移面方向**现场校准**, 不猜符号: 先探一小步(−2mm)复测, 量出"每移 1mm
     总长变多少"(带内含不含咀尖决定了正负, 各件不同 —— 用户两份日记里就
     有相反的例子), 再按斜率一步补齐, 移完复测、不齐再补(有轮数上限)。

失败兜底: 移面做不成/收敛不了时, **位置保持正确**, 只是保持新件原长,
日志写明差多少 —— 绝不出现"为对长度把位置搭进去"(v3.2 A 方案的教训:
放置先预偏移、赌移面把定位点带回来, 移面一失败件就整体偏 Δ)。
"""

import math

from cad3d.core.constants import (
    NOZZLE_FAMILIES,
    NOZZLE_KEEP_HEAD,
)

# 移面"那一带"半宽 = 定位点上下各 KEEP_HEAD/2(默认 30/2=15mm, 共 30) ——
# 用户录制的两份日记里, 移的面(−15/0/+13/+6.5 与 −72/−78.5/−85/−100)全落
# 在定位点 ±15 的带里; 带外的(顶尖、头背)不动。
_BAND_HALF = NOZZLE_KEEP_HEAD / 2.0
# 判定"水平面"(朝上/朝下)的 Z 跨度上限: 面围盒的 zmax−zmin 小于它就算
_FLAT_TOL = 0.1
# 方向校准探步(mm): 先移这一小步, 复测出"每移 1mm 总长变多少"
_PROBE_STEP = 2.0
# 斜率下限: |斜率| 低于它 = 移了面长度也不跟变(带内面不控制总长), 放弃
_SLOPE_MIN = 0.2
# 补差主循环轮数(每轮: 按当前斜率补齐 → 复测)
_MAX_STEPS = 6
# 整步提交失败后的子步上限(mm) —— 拆小步只是兜底, 正常一次到位
_MAX_STEP = 10.0
# 长度对齐判定容差(mm)
_LEN_TOL = 0.05


def is_nozzle(fname, families=None):
    """(纯逻辑) 文件名含热咀族任一关键词 → True。族表默认取 config。"""
    fams = NOZZLE_FAMILIES if families is None else families
    low = str(fname or "").lower()
    return any(str(k).lower() in low for k in (fams or []))


def pick_faces(face_boxes, center_z, half=None, flat_only=True, tol=0.01):
    """(纯逻辑) 挑出要移的面 —— **定位点上下 half 那一带里的水平面**。

    center_z = 定位点所在高度(= 放置点 Z, 件上那个定位面放置后就在这儿)。
    只选 Z 落在这个带里的**水平面**(朝上/朝下): 移它们就等于"把件在定位点
    这一段挪一挪", 拉长/缩短都从这一段出 —— 带外的(顶尖、头背)一律不动。

    ⭐ 用户 2026-09-18 两份录制日记佐证: 移的面 Z = −15/0/+13/+6.5(在原点
    调长)与 −72/−78.5/−85/−100(在模型里调, 定位点 −85), 全落在定位点 ±15
    带内; 头背与咀尖的端面都没动。
    侧面(圆柱外圆等)不选 —— 沿轴向平移侧壁没有几何意义。
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
    """去掉一组体的建模参数(变成哑体) —— 日记口径: 移面前先去参。

    两份录制日记里移面的对象全是 UNPARAMETERIZED 哑体; 提升体是 Wave 链接,
    不去参直接移面, 实机就报"面不再与先前的邻近对象相交"(大面积移面全挂的
    根因)。只处理传入的这几个体, 不动全局登记表(主流水线收尾还会统一去参)。
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
    (移面就地改, 体列表原样返回)。锚点就是**真实放置点**(没有预偏移):
    位置在放置那一刻就正确, 本钩子只管长度, 失败也不碰位置。
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
            _fix_z = float(anch[2])     # 定位点高度 = 放置点 Z(移面带的中心)
        except (TypeError, ValueError, IndexError):
            _fix_z = None

        def _measure():
            bbs = [_body_bbox(uf, t) for t in tools]
            t, b, how = plane_span(read_face_rows(uf, tools), _union_bbox(bbs))
            if t is None or b is None:
                return _len_of(bbs), how, None, None
            return (t - b), how, t, b

        def _band_faces():
            rows = read_face_rows(uf, tools)
            idxs = pick_faces([r[0] for r in rows], _fix_z)
            if not idxs:
                # 极端形状(这一带里一个水平面都没有) → 退回宽口径, 至少能动
                idxs = pick_faces([r[0] for r in rows], _fix_z, flat_only=False)
            return [rows[i][3] for i in idxs]

        def _move(amount):
            """移 amount(带符号)。整步失败且量大时拆 ≤_MAX_STEP 小步兜底。"""
            fs = _band_faces()
            if not fs:
                log("【长度对齐】%s 第 %d 处: 定位点±%.4g 那一带里没有可移的面。"
                    % (fname, idx, _BAND_HALF))
                return False
            if _move_faces_z(work_part, session, fs, amount, log):
                return True
            if abs(amount) <= _MAX_STEP:
                return False
            log("【长度对齐】%s 第 %d 处: 一步移 %.4g 没成, 拆成 ≤%.4g 小步重试。"
                % (fname, idx, amount, _MAX_STEP))
            n = math.ceil(abs(amount) / _MAX_STEP)
            small = amount / n
            for _k in range(n):
                fs2 = _band_faces()
                if not fs2 or not _move_faces_z(work_part, session, fs2,
                                                small, log):
                    return False
            return True

        # ① 去参数(日记口径: 移面只对哑体做; 链接体移面会报"面不再相交")
        _deparameterize_bodies(work_part, tools, log)

        # ② 量当前长度
        cur, how, t0, b0 = _measure()
        if cur is None:
            log("【长度对齐】%s 第 %d 处: 新件长度量不到, 保持原样(位置正确)。"
                % (fname, idx))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        log("【长度对齐】%s 第 %d 处: 新件 %d 个体, 按%s量 Z %.4g~%.4g → 长 %.4g"
            " (旧件 %.4g)" % (fname, idx, len(tools), how,
                              b0 if b0 is not None else float("nan"),
                              t0 if t0 is not None else float("nan"),
                              cur, old_len))
        if abs(old_len - cur) <= _LEN_TOL:
            log("【长度对齐】%s 第 %d 处: 新旧等长(都是 %.4g), 免调。"
                % (fname, idx, cur))
            return tools

        # ③ 探向: 先移一小步, 量出"每移 1mm 总长变多少"(符号各件不同, 不猜)
        if not _move(-_PROBE_STEP):
            log("【长度对齐】%s 第 %d 处: 探步就移不动, 保持新件原长 %.4g"
                "(位置正确, 与旧件差 %.4g)。"
                % (fname, idx, cur, old_len - cur))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        prev, cur = cur, _measure()[0]
        slope = calib_slope(prev, cur, -_PROBE_STEP)
        if cur is None or abs(slope) < _SLOPE_MIN:
            log("【长度对齐】%s 第 %d 处: 移了面总长没跟变(带内面不控制总长), "
                "已撤销不了, 保持现状(位置正确, 长度 %.4g, 旧件 %.4g)。"
                % (fname, idx, cur if cur is not None else float("nan"),
                   old_len))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools

        # ④ 按斜率补差 → 复测 → 不齐再补(每轮用上一轮实测重校斜率)
        done = False
        moved_total = -_PROBE_STEP
        for _r in range(_MAX_STEPS):
            step = step_for(old_len, cur, slope)
            if step == 0.0:
                done = True
                break
            if not _move(step):
                log("【长度对齐】%s 第 %d 处: 移面提交失败, 保持现状(位置正确, "
                    "长 %.4g, 旧件 %.4g, 还差 %.4g)。"
                    % (fname, idx, cur, old_len, old_len - cur))
                break
            moved_total += step
            prev, cur = cur, _measure()[0]
            if cur is None:
                break
            _s2 = calib_slope(prev, cur, step)
            if abs(_s2) >= _SLOPE_MIN:
                slope = _s2
            if abs(old_len - cur) <= _LEN_TOL:
                done = True
                break

        if done and cur is not None and abs(old_len - cur) <= _LEN_TOL:
            adj_stats["adj"] = adj_stats.get("adj", 0) + 1
            log("【长度对齐】%s 第 %d 处: 对齐完成 —— 总长 %.4g = 旧件 %.4g"
                "(带内共移 %.4g mm, 方向斜率 %.4g)。"
                % (fname, idx, cur, old_len, moved_total, slope))
        else:
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            log("【长度对齐】%s 第 %d 处: 没收敛 —— 现在 %.4g, 旧件 %.4g, "
                "还差 %.4g。位置是正确的, 长度请按日志数字手动收尾"
                "(移动面选定位点±%.4g 带内的面)。"
                % (fname, idx, cur if cur is not None else float("nan"),
                   old_len,
                   (old_len - cur) if cur is not None else float("nan"),
                   _BAND_HALF))
        return tools

    return hook
