# -*- coding: utf-8 -*-
"""cad3d.modeling.nozzle_len —— 热咀替换时按旧件长度调整新件长度。

口径 = 用户手动做法(2026-09-18 定案): 替换热咀时, 头部(顶部往下
NOZZLE_KEEP_HEAD mm 这一段)不动, 其余部分用"移动"整体平移, 让新件
"顶部到底部"的总长对齐被换掉的旧件 —— 新件比旧件短就拉长, 比旧件长
就缩短。旧件长度 = 旧件标准件体的顶部到底部(世界 Z, 包围盒口径)。

实现: 热咀 .prt 每处实例常为多实体(头部体 + 咀身/咀尖体)。对"完全落在
头部带以下"的体, 用同款 .prt 组件在平移后的位置再装一次 → 只提升对应
序号的体 → 校验包围盒恰好 = 原体 + 平移量 → 换掉原体。全部用主流水线
已在用的接口(装组件/提升/批量删), 不依赖同步建模等跨版本不可用 API。
"""

import os

from cad3d.core.constants import (
    COMP_PREFIX,
    FEATURE_PREFIX,
    NOZZLE_FAMILIES,
    NOZZLE_KEEP_HEAD,
    NOZZLE_LEN_TOL,
)
from cad3d.core.paths import stdparts_dir

_EQUAL_NOTE = "新旧等长, 免调"


def is_nozzle(fname, families=None):
    """(纯逻辑) 文件名含热咀族任一关键词 → True。族表默认取 config。"""
    fams = NOZZLE_FAMILIES if families is None else families
    low = str(fname or "").lower()
    return any(str(k).lower() in low for k in (fams or []))


def plan_shift(old_len, bboxes, axis_sign, keep_head=None, tol=None):
    """(纯逻辑) 旧件长度 + 新件实例各体世界包围盒 + 头端朝向 → 平移计划。

    返回 (shift, keep, move, note):
      shift = None → 不用/不能调(note 说原因), 此时 keep/move 为空;
      否则 shift 为沿世界 Z 的平移量(mm), keep 里的体(头部段)不动,
      move 里的体整体平移 shift —— 平移后实例总长 = old_len。
    axis_sign: +1 = 头在顶端(+Z 插入), -1 = 头在底端(-Z 翻转插入)。
    头部段定义: 伸进"头端起 keep_head 高度带"的体都算头部(手动选区同款:
    顶部往下 30mm 范围不动); 没有体完全落在头部带以下时退化为"只留头端
    体"(体含全局顶/底极值者), 其余平移。
    """
    keep_head = NOZZLE_KEEP_HEAD if keep_head is None else float(keep_head)
    tol = NOZZLE_LEN_TOL if tol is None else float(tol)
    if old_len is None:
        return None, [], [], "旧件长度没找到, 不调长度"
    try:
        old_len = float(old_len)
    except (TypeError, ValueError):
        return None, [], [], "旧件长度读不出来, 不调长度"
    if old_len <= 0:
        return None, [], [], "旧件长度不是正数, 不调长度"
    vals = []
    for b in (bboxes or []):
        if not b or len(b) < 6:
            return None, [], [], "新件有体的包围盒读不到, 不调长度"
        vals.append((float(b[0]), float(b[1]), float(b[2]),
                     float(b[3]), float(b[4]), float(b[5])))
    if not vals:
        return None, [], [], "新件没有实体, 不调长度"
    top = max(b[5] for b in vals)
    bot = min(b[2] for b in vals)
    new_len = top - bot
    shift = (1.0 if axis_sign >= 0 else -1.0) * (new_len - old_len)
    if abs(shift) <= tol:
        return None, [], [], _EQUAL_NOTE
    if len(vals) < 2:
        return (None, [], [],
                ("单实体没法只动下半段, 请手动: 头部往下 30mm 以下用移动命令"
                 "对齐旧件长度"))
    if axis_sign >= 0:
        cut = top - keep_head
        keep = [i for i, b in enumerate(vals) if b[5] > cut + tol]
    else:
        cut = bot + keep_head
        keep = [i for i, b in enumerate(vals) if b[2] < cut - tol]
    if keep and len(keep) < len(vals):
        move = [i for i in range(len(vals)) if i not in keep]
        return shift, keep, move, ""
    # 没有体完全落在头部带以下(头很短/全部跨界): 只留头端体, 其余平移
    head = (max(range(len(vals)), key=lambda i: vals[i][5]) if axis_sign >= 0
            else min(range(len(vals)), key=lambda i: vals[i][2]))
    move = [i for i in range(len(vals)) if i != head]
    return shift, [head], move, "各体都伸进头部带, 按只留头端体平移其余"


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


def make_nozzle_hook(session, work_part, params, old_lens, log, adj_stats=None):
    """造一个 place_std_parts 的 placed_hook: 放好的热咀按旧件长度对齐。

    old_lens: [(锚点(x,y,z,..), 旧件实例长度), ...] —— 替换入口按旧件体
    分组算好传入; adj_stats: 可变 dict, 回填 adj/skip 计数供报告。
    hook 签名 (fname, 序号, 锚点, 规则, 体列表, 待删组件列表) → 新体列表;
    出错时本处实例保持原样不动(临时组件由 place_std_parts 段2 统一清理)。
    """
    import NXOpen as nx

    from cad3d.modeling.nx_compat import _mark_type, _matrix3x3
    from cad3d.modeling.std_rules import _std_z
    from cad3d.modeling.stdparts import (
        _batch_delete,
        _mark_anchor,
        _place_delta,
        _promote_body,
    )

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

    def _bbox_pair_ok(bb_new, bb_old, shift_z):
        if not bb_new or not bb_old or len(bb_new) < 6 or len(bb_old) < 6:
            return False
        for k2 in range(6):
            want = float(bb_old[k2]) + (shift_z if k2 in (2, 5) else 0.0)
            if abs(float(bb_new[k2]) - want) > 0.05:
                return False
        return True

    def hook(fname, idx, anch, rule, tools, pending_comps):
        if uf is None or _body_bbox is None or not tools:
            return tools
        if not is_nozzle(fname):
            return tools
        old_len = nearest_anchor_len(anch, old_lens)
        bboxes = [_body_bbox(uf, t) for t in tools]
        axis_sign = -1.0 if rule.get("dir") == "-Z" else 1.0
        shift, _keep, move, note = plan_shift(old_len, bboxes, axis_sign)
        if shift is None:
            log("【长度对齐】%s 第 %d 处: %s。" % (fname, idx, note))
            if note != _EQUAL_NOTE:
                adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        if note:
            log("【长度对齐】%s 第 %d 处: %s。" % (fname, idx, note))

        # 与 place_std_parts 同口径重算本实例的放置位姿, 再沿世界 Z 平移 shift
        ca = work_part.ComponentAssembly
        flip = (rule["dir"] == "-Z")
        z_rule = _std_z(params, rule)
        try:
            z_i = z_rule if anch[2] is None else float(anch[2])
        except (TypeError, ValueError, IndexError):
            z_i = z_rule
        cx, cy = float(anch[0]), float(anch[1])
        m3 = _matrix3x3(nx, flip, 0.0)      # 热咀非 YXB 逐板判向件, 角度恒 0
        dx, dy, dz = _place_delta(rule.get("ref"), flip,
                                  (float(rule.get("off_x", 0.0)),
                                   float(rule.get("off_y", 0.0)),
                                   float(rule.get("off_z", 0.0))))
        path = os.path.join(stdparts_dir(), fname)
        stem = os.path.splitext(fname)[0]
        comp_name = "%s%s_%d_LEN" % (COMP_PREFIX, stem, idx)
        replaced, to_del = {}, []
        try:
            pos2 = nx.Point3d(cx + dx, cy + dy, z_i + dz + shift)
            try:
                comp2, _ls = ca.AddComponent(path, "MODEL", comp_name,
                                             pos2, m3, -1)
            except TypeError:
                comp2 = ca.AddComponent(path, "MODEL", comp_name,
                                        pos2, m3, -1, False)
            pending_comps.append(comp2)     # 临时组件随段2 一次删
            for j in move:
                nb = _promote_body(work_part, comp2,
                                   "%sBODY_%s_%d_LEN%d" % (FEATURE_PREFIX, stem,
                                                           idx, j + 1),
                                   log, body_index=j)
                if nb is None:
                    raise RuntimeError("第 %d 个体提升失败" % (j + 1))
                if not _bbox_pair_ok(_body_bbox(uf, nb), bboxes[j], shift):
                    raise RuntimeError("平移后的包围盒对不上(体序号 %d)" % (j + 1))
                _mark_type(nb, "STD:" + fname)
                _mark_anchor(nb, (cx, cy, z_i), 0.0, uf)
                replaced[j] = nb
                to_del.append(tools[j])
        except Exception as ex:
            # 本实例回滚: 换上的新体删掉, 原体保持原样(组件交由段2 清理)
            log("【长度对齐】%s 第 %d 处失败(%s), 这一处保持原长不动。"
                % (fname, idx, ex))
            _batch_delete(session, list(replaced.values()), log, "长度对齐失败体")
            adj_stats["skip"] = adj_stats.get("skip", 0) + 1
            return tools
        out = list(tools)
        for j, nb in replaced.items():
            out[j] = nb
        _batch_delete(session, to_del, log, "长度对齐换下的原体")
        adj_stats["adj"] = adj_stats.get("adj", 0) + 1
        new_len = (max(b[5] for b in bboxes if b) - min(b[2] for b in bboxes if b)
                   if all(b for b in bboxes) else 0.0)
        log("【长度对齐】%s 第 %d 处: 旧件长 %.4g, 新件原长 %.4g → 咀身平移"
            " %.4g mm 对齐(头部 %.4g mm 一段不动)。"
            % (fname, idx, old_len, new_len, -shift, NOZZLE_KEEP_HEAD))
        return out

    return hook
