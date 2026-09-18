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


def plan_shift(old_len, bboxes, axis_sign, keep_head=None, tol=None):
    """(纯逻辑) 旧件长度 + 新件各体世界包围盒 + 头端朝向 → 移面量与分界高度。

    axis_sign: +1 = 头在顶端(+Z 插入), -1 = 头在底端(-Z 翻转插入)。
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
    top = max(b[5] for b in vals)
    bot = min(b[2] for b in vals)
    new_len = top - bot
    shift = (1.0 if axis_sign >= 0 else -1.0) * (new_len - old_len)
    cut = (top - keep_head) if axis_sign >= 0 else (bot + keep_head)
    if abs(shift) <= tol:
        # 带上实测长度: 只报"免调"看不到数字, 量得对不对没法核对
        return None, None, "%s(都是 %.4g), 免调" % (_EQUAL_NOTE, new_len)
    return shift, cut, ""


def pick_faces(face_boxes, cut, axis_sign, tol=0.01, flat_tol=0.1,
               flat_only=True):
    """(纯逻辑) 挑出要跟着平移的面下标 —— 两道闸都要过。

    ① **整块**落在头部带以下: 面的 Z 高端 ≤ cut(头在顶) / 低端 ≥ cut(头在底);
    ② **是"水平面"**: 面的包围盒 Z 跨度 ≤ flat_tol —— 也就是朝上/朝下的底面、
       台阶面, 它们垂直于平移方向, 移它们才是有意义的几何操作。

    ⚠️ 侧面(圆柱外圆、侧壁)一律**不选**。沿轴向平移一个侧壁本身没有几何意义,
    NX 要么拒绝要么给出不干净的几何 —— **这正是"长度总差那么一点"的根因**。
    侧壁交给 NX 自己"延伸相邻面"补上, 与手动做法完全一致: 用户 2026-09-18
    录制的日记里, 一次只选了 **4 块面**(来自 2 个体), 全是朝上/朝下的面,
    侧壁一块都没选。

    flat_only=False 时跳过闸②(留给"一个水平面都没有"的极端形状保底)。
    """
    out = []
    for i, b in enumerate(face_boxes or []):
        if not b or len(b) < 6:
            continue
        z_lo, z_hi = float(b[2]), float(b[5])
        if flat_only and (z_hi - z_lo) > flat_tol:
            continue
        if axis_sign >= 0:
            if z_hi <= cut + tol:
                out.append(i)
        elif z_lo >= cut - tol:
            out.append(i)
    return out


def next_step(old_len, cur_len, axis_sign, tol=None):
    """(纯逻辑) 复测出来的残差 → 这一轮该沿世界 Z 移多少; 已经够准就返回 0。

    头在顶端(+Z 插入)时"往下移 = 变长", 所以移量 = -(还差的长); 头在底端
    (-Z 翻转)反过来。符号搞反会越移越远, 所以单独抽出来测。
    """
    tol = _LEN_TOL if tol is None else float(tol)
    try:
        need = float(old_len) - float(cur_len)      # 正 = 还要再变长
    except (TypeError, ValueError):
        return 0.0
    if abs(need) <= tol:
        return 0.0
    return -need if axis_sign >= 0 else need


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


def _face_boxes(uf, tool):
    """一个体的全部面 → [(面对象, 面包围盒6), ...](读不到的跳过)。"""
    from cad3d.modeling.jrt import _uf_face_data
    out = []
    try:
        faces = list(tool.GetFaces())
    except Exception:
        return out
    for f in faces:
        try:
            bb = _uf_face_data(uf, f)[3]
            if bb and len(bb) >= 6:
                out.append((f, bb))
        except Exception:
            continue
    return out


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
        for attr, val in (("RelationScope", 1023), ("CloneScope", 511),
                          ("UseFindClone", True), ("UseFindRelated", True),
                          ("UseFaceBrowse", True),
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
        axis_sign = -1.0 if rule.get("dir") == "-Z" else 1.0
        shift, cut, note = plan_shift(old_len, bboxes, axis_sign)
        if shift is None:
            log("【长度对齐】%s 第 %d 处: %s。" % (fname, idx, note))
            if not note.startswith(_EQUAL_NOTE):
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        new_len0 = _len_of(bboxes)
        # 逐根打"这一根是怎么量出来的": 每个体自己的 Z 范围 + 合出来的总长。
        # 每根热咀长度都可能不同, 长度对不上时先看这行就知道是哪个体不对
        log("【长度对齐】%s 第 %d 处: 新件 %d 个体, Z=%s → 总长 %.4g"
            % (fname, idx, len(tools),
               " / ".join("%.4g~%.4g" % (b[2], b[5])
                          for b in bboxes if b and len(b) >= 6),
               new_len0 if new_len0 is not None else float("nan")))

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
            pairs = []
            for t in tools:                          # 每轮重取: 移面后几何与面都变了
                pairs.extend(_face_boxes(uf, t))
            idxs = pick_faces([bb for _f, bb in pairs], cut, axis_sign)
            if not idxs:
                # 极端形状(一个朝上/朝下的面都没有) → 退回宽口径, 至少能动
                idxs = pick_faces([bb for _f, bb in pairs], cut, axis_sign,
                                  flat_only=False)
            faces = [pairs[i][0] for i in idxs]
            if not faces:
                log("【长度对齐】%s 第 %d 处: 头部带以下没有可移的面(旧件长 %.4g, "
                    "新件长 %.4g), 这处保持原长。" % (fname, idx, old_len, cur))
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
                return tools
            if not _move_faces_z(work_part, session, faces, step, log):
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
                return tools
            moved += len(faces)
            cur = _len_of([_body_bbox(uf, t) for t in tools])

        if cur is None or abs(cur - old_len) > _LEN_TOL:
            log("【长度对齐】%s 第 %d 处: 移面后长 %.4g ≠ 旧件 %.4g(还差 %.4g), "
                "已留下改动供你核对(体没换, 只动了几块面)。"
                % (fname, idx, cur if cur is not None else float("nan"),
                   old_len, (cur - old_len) if cur is not None else float("nan")))
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        adj_stats["adj"] = adj_stats.get("adj", 0) + 1
        log("【长度对齐】%s 第 %d 处: 旧件长 %.4g, 新件原长 %.4g(新件 %d 个体)"
            " → 净拉长 %.4g mm 对齐(头部 %.4g mm 一段不动, 动了 %d 块面)。"
            % (fname, idx, old_len, new_len0, len(tools), old_len - new_len0,
               NOZZLE_KEEP_HEAD, moved))
        return tools

    return hook


def _len_of(bboxes):
    """[(包围盒6)] → 世界 Z 总高; 缺盒/空 → None。"""
    vals = [b for b in (bboxes or []) if b and len(b) >= 6]
    if not vals:
        return None
    return max(float(b[5]) for b in vals) - min(float(b[2]) for b in vals)
