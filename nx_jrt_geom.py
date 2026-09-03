# -*- coding: utf-8 -*-
"""
nx_jrt_geom.py —— 加热条(JRT)几何判据(纯逻辑, 可离线测, 无 NX 依赖)
========================================================================

拆分自 nx_extrude_runner.py(§5.6 JRT 里的纯判据函数)。异形判据全部来自
实物实证(docs/AGENTS.md §4 坑点 12-14, 勿凭直觉推翻):
  - 面体检: 退化碎片面(bbox 零维>=2)=异形; 型20/23 样条面是样条墙+拔模
    几何的正常产物, 不算异形(v1.24/01.dxf 实证);
  - 圆顶判据: 体内残留型20 样条拔模面=异形(jrt2.prt 六状态实测定案);
  - 体积: 正常 G1 全长滚圆丢体约 11%, 阈值只能拦粗大异常(>25% 或 <=0);
  - 删面锚点: 出线口线中点 / 收口连接线(最短2条 + 短直线泛化);
  - 开链修复: 断口<=1mm 桥接, 大缺口不桥(直线桥包怪条)。

本模块不 import NXOpen(_body_face_rows 只经参数 uf 取面数据)。
"""

import math
from collections import Counter


def _jrt_sides(z_start, z_end, bottom):
    """加热条两侧区间: 顶侧=(start,end); 底侧=底面镜像(入侵量=end-start)。

    (与期刊"镜像到板另一侧"工序等效: 两侧对称。)
    """
    intr = z_end - z_start                      # 顶侧入侵量(带方向)
    return [("T", z_start, z_end), ("B", bottom, bottom - intr)]


def _faces_healthy(rows):
    """(纯逻辑, 可离线测) 条体面体检: rows=(类型, 半径, bbox零维数) 列表。

    好(不异形) ⇔ 无退化碎片面。平面(bbox)必有 1 个零维(法向厚度)
    ——正常; 零维≥2 = 线/点状碎片(删面愈合残留实证)。
    型20/型23 样条面是样条墙+拔模几何下的正常产物(01.dxf 实证),
    不算异形; 倒圆翻卷由体积阈值兜底。返回 (是否健康, 问题描述)。
    """
    for ftype, r, zc in rows:
        if zc >= 2:
            return False, "退化碎片面(零维%d个)" % zc
    return True, ""


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


def _flush_start_r(blend_r, r_min, thickness):
    """(纯逻辑, 可离线测) 齐平端倒圆起试半径 = min(边倒圆R, 条厚/2−0.05),
    不低于 r_min。

    【当前未接入流水线】v1.26 的逐R对照实验(exp_r)证伪了"2R>条厚即异形"
    这一前提(R3.7 反而产样条面、R3.9 全解析), 厚度预防式起试半径已回退,
    build_jrt 现在直接从边倒圆R 起试(靠体积/面体检网络兜底降R)。
    保留本函数+自测供后续再实验, 调用侧接入前先确认前提成立。
    """
    return max(float(r_min),
               min(float(blend_r), float(thickness) / 2.0 - 0.05))


def _dome_body_ok(rows):
    """(纯逻辑, 可离线测) 圆顶(齐平端)倒圆后体判据——jrt2.prt 六状态
    实测定案(用户制造): 异形(C/D, R3.9/3.8) ⇔ 体内残留 型20 样条拔模
    面×2(顶面倒圆未吞并侧壁); 干净(E/F, R3.7/完整体) 型20=0, 且 E 的
    型23 反而更多 → 型23 不是判据。rows=(类型, ...) 列表。
    返回 (是否合格, 问题描述)。"""
    n20 = sum(1 for row in rows if row[0] == 20)
    if n20:
        return False, "残留样条拔模面%d片(侧壁未被倒圆吞并)" % n20
    return True, ""


def _blend_ok(vol_before, vol_after):
    """(纯逻辑, 可离线测) 倒圆结果是否正常(不异形)。

    基准样板(3Djrttest)实证: 正常 G1 切链倒圆会沿侧壁全长滚过,
    丢体可达 11% —— 阈值不能定在个位数百分比。只拦【粗大异常】:
    体积<=0 或 丢体>25%(真翻卷是此量级的几十倍)。体积测不到不拦
    (保持旧行为)。
    """
    if vol_before is None or vol_after is None:
        return True                     # 测不到 → 不拦(旧行为)
    if vol_after <= 0.0:
        return False
    return vol_after >= vol_before * 0.75


def _chain_tips(chain, ents):
    """(纯逻辑) 链的断口端点(只出现一次的端点)。"""
    from collections import Counter
    pts = []
    for i, _r in chain:
        e = ents[i]
        pts += [e.p1, e.p2]
    cnt = Counter((round(x, 3), round(y, 3)) for x, y in pts)
    return [p for p, c in cnt.items() if c == 1]


def _cluster_tips(tips, tol):
    """(纯逻辑) 断点按 ≤tol 聚类 → [[点,...], ...]。"""
    clusters = []
    for p in tips:
        for c in clusters:
            if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol for q in c):
                c.append(p)
                break
        else:
            clusters.append([p])
    return clusters


def _chain_outlet_mids(chain, ents):
    """(纯逻辑, 可离线测) 出线口线中点——链上的短线段(≤15mm)且链序
    前后两邻都是线(两出线口环形通道的 8mm 口线一案; 期刊删除面正位于
    口线中点处)。跨接线(邻有弧)不在此列。"""
    mids = []
    for k, (i, _r) in enumerate(chain):
        e = ents[i]
        if e.kind != "line":
            continue
        L = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1])
        if L > 15.0:
            continue
        pa = ents[chain[(k - 1) % len(chain)][0]]
        pb = ents[chain[(k + 1) % len(chain)][0]]
        if pa.kind == "line" and pb.kind == "line":
            mids.append(((e.p1[0] + e.p2[0]) / 2.0,
                         (e.p1[1] + e.p2[1]) / 2.0))
    return mids


def _chain_connectors(chain, ents, ratio=0.3):
    """链中的收口连接线(内外轮廓环之间的短直线) → [(中点X, 中点Y), ...]。

    期刊实测: 删面位置 = 两条连接线旁的倒圆面(面中心距连接线中点≈1)。
    判定: 最短的 2 条直线, 且长度 < ratio×其余直线中位长度。
    """
    lines = []
    for k, (i, _r) in enumerate(chain):
        e = ents[i]
        if e.kind != "line":
            continue
        L = math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1])
        # 相邻段(链序前后各一, 环回)
        pa = ents[chain[(k - 1) % len(chain)][0]]
        pb = ents[chain[(k + 1) % len(chain)][0]]
        two_lines = pa.kind == "line" and pb.kind == "line"
        lines.append((L, (e.p1[0] + e.p2[0]) / 2.0,
                      (e.p1[1] + e.p2[1]) / 2.0,
                      not two_lines))
    if len(lines) < 3:
        return []
    srt = sorted(lines, key=lambda t: t[0])
    rest = [t[0] for t in srt[2:]]
    med = sorted(rest)[len(rest) // 2]
    if srt[0][0] < ratio * med and srt[1][0] < ratio * med:
        return [(srt[0][1], srt[0][2]), (srt[1][1], srt[1][2])]
    # 泛化(01.dxf 两出线口环形通道一案): 跨接线=短直线(≤15mm, 通道
    # 宽度量级)且至少一侧邻是弧且不处于 线-线-线 连续段(8mm 口线
    # 两侧邻都是线 → 排除; 6.09 跨接线 [弧,线] → 命中)
    cands = [(t[1], t[2]) for t in lines
             if t[0] <= 15.0 and t[3]]
    if 2 <= len(cands) <= 8:
        return cands
    return []


def _conn_face_pick(face_rows, conn_mids, r_ref):
    """(纯逻辑, 可离线测) 从面行 (tag, cx, cy, 半径) 中为每个连接线中点
    挑删面。只认【圆柱面且半径≈倒圆R】的倒圆面; 距离门控
    2.5×R+2(期刊实测面中心距连接线中点≈1)——任一连接线找不到可信面
    即整组放弃(删错面会毁掉整根条, 宁可不删)。返回 [tag,...] 或 None。"""
    r_ref = float(r_ref or 0.0)
    tol_r = max(0.3, 0.25 * r_ref) if r_ref > 1e-9 else 1e18
    gate = 2.5 * max(r_ref, 1.0) + 2.0
    pool = [r for r in face_rows
            if r[3] > 1e-9 and abs(r[3] - r_ref) <= tol_r]
    picks, used = [], set()
    for (mx, my) in conn_mids:
        best, bd = None, None
        for row in pool:
            if row[0] in used:
                continue
            d = math.hypot(row[1] - mx, row[2] - my)
            if best is None or d < bd:
                best, bd = row, d
        if best is None or bd > gate:
            return None
        picks.append(best[0])
        used.add(best[0])
    return picks


def _merge_open_chains(opens, ents, tol=1.0, bridge_max=1.0):
    """(纯逻辑, 可离线测) 修复开链(手动拉伸能成功而脚本判开一案):

    ①并组: 断口互相贴近(≤tol)的开链并成一组(123.dxf 实测 0.24mm 接缝,
      链容差 0.01 没并上);
    ②闭合判定: 组内断点聚类(≤tol)后——
        无断点 → 已闭合, 计入闭链;
        簇形态可闭合 ⇔ 无 >2 点簇 且 单点簇恰 0 个 且 每簇缝隙≤bridge_max:
            双点簇 = 接缝缝隙(0.24mm 级) → 每簇一条桥接线;
            大缺口(缺整条边, 25mm 级)【不桥】——直线桥会横穿其它轮廓
            包出数倍体积的怪条/无效截面(实测一案), 放弃并记断口坐标,
            由用户在 2D 补线(手动拉伸同样需要先补)。
    返回 (closed_extra, bridge_jobs, open_logs):
      closed_extra = [(i, False), ...] 形链
      bridge_jobs  = [(链, [(端1, 端2, 缺口长), ...]), ...]
      open_logs    = [(段数, 断口点...), ...]
    """
    groups = [[[tuple(it) for it in o]] for o in opens]
    changed = True
    while changed:
        changed = False
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                ta = []
                for ch in groups[a]:
                    ta += _chain_tips([(i, False) for i, _r in ch], ents)
                tb = []
                for ch in groups[b]:
                    tb += _chain_tips([(i, False) for i, _r in ch], ents)
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
                       for p in ta for q in tb):
                    groups[a] += groups[b]
                    del groups[b]
                    changed = True
                    break
            if changed:
                break
    closed_extra, bridge_jobs, open_logs = [], [], []
    for g in groups:
        flat = [it for ch in g for it in ch]
        tips = _chain_tips([(i, False) for i, _r in flat], ents)
        if not tips:
            closed_extra.append(flat)
            continue
        clusters = _cluster_tips(tips, tol)
        singles = [c for c in clusters if len(c) == 1]
        twins = [c for c in clusters if len(c) == 2]
        bad = [c for c in clusters if len(c) > 2]
        pairs = []
        if bad or singles:
            # 断口形态不可闭合(3+点簇 / 存在单点簇=缺边级大缺口)
            open_logs.append((len(flat), tips))
            continue
        for c in twins:                       # 仅小缝(≤bridge_max)桥接
            p, q = c[0], c[1]
            gap = math.hypot(p[0] - q[0], p[1] - q[1])
            if gap > bridge_max:
                open_logs.append((len(flat), tips))
                pairs = None
                break
            pairs.append((p, q, gap))
        if pairs is None:
            continue
        bridge_jobs.append((flat, pairs))
    return closed_extra, bridge_jobs, open_logs
