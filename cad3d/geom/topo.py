# -*- coding: utf-8 -*-
"""cad3d.geom.topo —— 环链几何拓扑、轮廓组织与锚点提取。"""

import math
from collections import defaultdict
from cad3d.core.constants import LOOP_TOL, LAYER_CODES


def _pkey(p, tol=LOOP_TOL):
    return (int(round(p[0] / tol)), int(round(p[1] / tol)))


def _near_keys(p, tol=LOOP_TOL):
    """端点所在量化桶及 3×3 邻桶。

    (v1.35) 此前只查单桶: 两点间距 <tol 但跨量化格边界时永远配不上,
    该闭合的链被判开 → 轮廓不拉伸/JRT 多画桥接线。
    """
    kx, ky = _pkey(p, tol)
    return [(kx + dx, ky + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def find_chains(segs):
    """把线/弧按端点重合连成链(容差 LOOP_TOL, 3×3 邻桶搜索)。

    返回 (closed, open_): closed=[[(idx, rev), ...] 每项为(曲线索引, 是否反向)],
    闭合链首尾相接; open_ 为两端悬空的链。
    (v1.35) 端点三叉及以上(T 形相接/重复线)时, 不再按字典序任意配对,
    优先取"方向延续性最好"的段——纯任意配对会把两条共端点轮廓串成错链。
    """
    ep = defaultdict(list)
    for i, s in enumerate(segs):
        if s.kind == "circle":
            continue
        ep[_pkey(s.p1)].append((i, 0))
        ep[_pkey(s.p2)].append((i, 1))

    used = [False] * len(segs)

    def _take(pt, prev_pt):
        """邻桶内找未用段: 与链方向延续性最好、其次距离最近的端点配对。"""
        vx = pt[0] - prev_pt[0]
        vy = pt[1] - prev_pt[1]
        vlen = math.hypot(vx, vy)
        best = None
        for k in _near_keys(pt):
            for (j, e) in ep.get(k, ()):
                if used[j]:
                    continue
                q = segs[j].p1 if e == 0 else segs[j].p2
                d = math.hypot(q[0] - pt[0], q[1] - pt[1])
                if d > LOOP_TOL:
                    continue
                other = segs[j].p2 if e == 0 else segs[j].p1
                ux, uy = other[0] - q[0], other[1] - q[1]
                ulen = math.hypot(ux, uy)
                # turn=1−cosθ: 直线延续→0, 折返→2; 无方向(链首)时 0.5 中性
                if vlen > 1e-12 and ulen > 1e-12:
                    turn = 1.0 - (ux * vx + uy * vy) / (ulen * vlen)
                else:
                    turn = 0.5
                cand = (turn, d, j, e)
                if best is None or cand[:2] < best[:2]:
                    best = cand
        if best is None:
            return None
        _turn, _d, j, e = best
        used[j] = True
        return j, e

    closed, open_ = [], []
    for i in range(len(segs)):
        if used[i] or segs[i].kind == "circle":
            continue
        used[i] = True
        chain = [(i, False)]
        # 从链头(i 的 p1)与链尾(i 的 p2)双向延伸
        for direction in ("tail", "head"):
            pt = segs[i].p1 if direction == "tail" else segs[i].p2
            prev_pt = segs[i].p2 if direction == "tail" else segs[i].p1
            forward = direction == "head"
            while True:
                got = _take(pt, prev_pt)
                if got is None:
                    break
                j, e = got
                # e: 曲线 j 与当前链端相连的端(0=p1, 1=p2); 判定进入方向
                rev = (e == 1)
                if forward:
                    chain.append((j, rev))
                else:
                    chain.insert(0, (j, not rev))
                prev_pt = pt
                pt = segs[j].p1 if e == 1 else segs[j].p2
        head_pt = segs[chain[0][0]].p1 if not chain[0][1] else segs[chain[0][0]].p2
        tail_pt = segs[chain[-1][0]].p2 if not chain[-1][1] else segs[chain[-1][0]].p1
        if _pkey(head_pt) == _pkey(tail_pt):
            closed.append(chain)
        else:
            open_.append(chain)
    return closed, open_


def loop_polygon(chain, segs, arc_step_deg=10.0):
    """把链离散为多边形顶点序列(用于包含测试/面积), 按链遍历方向。"""
    pts = []
    for idx, rev in chain:
        s = segs[idx]
        if s.kind == "line":
            a, b = (s.p2, s.p1) if rev else (s.p1, s.p2)
            if not pts:
                pts.append(a)
            pts.append(b)
        else:  # arc
            a0, a1 = s.a0, s.a1
            if rev:
                a0, a1 = a1, a0
            if not pts:
                pts.append((s.c[0] + s.r * math.cos(a0), s.c[1] + s.r * math.sin(a0)))
            span = a1 - a0
            steps = max(2, int(math.ceil(abs(span) / math.radians(arc_step_deg))))
            for k in range(1, steps + 1):
                ang = a0 + span * k / steps
                pts.append((s.c[0] + s.r * math.cos(ang), s.c[1] + s.r * math.sin(ang)))
    return pts


def poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _bbox(poly):
    if not poly:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xx = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xx:
                inside = not inside
        j = i
    return inside


def _loop_in_loop(poly_a, poly_b, samples=8):
    """环 A 是否被环 B 包含: 取 A 的至多 samples 个顶点投票(射线法)。

    (v1.35) 此前只用 A 的首顶点——首顶点恰落在 B 的边上(相切/共边)时
    判定随机; 多点投票对"真包含"(多数点在内)与"部分重叠"(少数点在内)
    区分更稳。
    """
    n = len(poly_a)
    step = max(1, n // samples)
    pts = poly_a[::step][:samples]
    hits = sum(1 for p in pts if point_in_poly(p, poly_b))
    return hits * 2 > len(pts)


def organize_loops(segs):
    """图层曲线 → 轮廓组织。

    返回 (profiles, opens, n_circles):
      profiles = [{"outer": poly, "outer_chain": chain, "holes": [(chain, poly), ...]}, ...]
      opens    = 开口链列表(警告用)
      圆独立成 profile(无 holes)。
    """
    closed, opens = find_chains(segs)
    loops = []
    for chain in closed:
        poly = loop_polygon(chain, segs)
        if len(poly) < 3:
            continue
        loops.append({"chain": chain, "poly": poly, "area": abs(poly_area(poly)),
                      "bbox": _bbox(poly)})
    for s in segs:
        if s.kind == "circle":
            cx, cy = s.c
            r = s.r
            # 圆用 8 边形近似即可满足包含/面积判定
            poly = [(cx + r * math.cos(math.pi / 4 * k), cy + r * math.sin(math.pi / 4 * k))
                    for k in range(8)]
            loops.append({"chain": None, "circle": s, "poly": poly,
                          "area": math.pi * r * r, "bbox": _bbox(poly)})

    # 重复描线去重(v1.35): 完全重合的环只留一个——重复环会被"最小包含
    # 环"逻辑判成第一个环的孔, 材料被错误掏空(AutoCAD 双重描线常见)。
    # 键取环顶点序列的规范化形式(起点取最小顶点+两个绕向取小),
    # 使同一几何的重复环即使链起点不同也能判重。
    def _canon_ring(pts):
        m = min(range(len(pts)), key=lambda t: pts[t])
        r = pts[m:] + pts[:m]
        return tuple((round(x, 3), round(y, 3)) for x, y in r)

    _seen_poly = set()
    _uniq = []
    for lp in loops:
        _p = lp["poly"]
        _k = min(_canon_ring(_p), _canon_ring(_p[::-1]))
        if _k in _seen_poly:
            continue
        _seen_poly.add(_k)
        _uniq.append(lp)
    loops = _uniq

    # 嵌套: 面积降序, 每环找包含它的【最小】外环 → 父子深度
    # v1.29 修复: 过去按 j=0.. 正序扫描(=面积由大到小)取第一个命中, 拿到的
    # 是"最大的包含环" —— 三层嵌套(A⊃B⊃C)时 C 的父环被判成 A 而非 B,
    # depth(C)=1 被当成 A 的第二个孔 → 岛的材料被错误减掉(应独立成体)。
    # 改为 j=i-1.. 逆序扫描(=面积由小到大), 第一个命中即最小包含环,
    # depth(C)=2 → 独立轮廓(下面"岛"分支才真正生效)。
    loops.sort(key=lambda d: -d["area"])
    parent = [-1] * len(loops)
    for i in range(len(loops)):
        bi0, bi1, bi2, bi3 = loops[i]["bbox"]
        for j in range(i - 1, -1, -1):  # j 面积更大; 逆序=先试最小的
            bj0, bj1, bj2, bj3 = loops[j]["bbox"]
            if bi0 >= bj0 and bi1 >= bj1 and bi2 <= bj2 and bi3 <= bj3 \
                    and _loop_in_loop(loops[i]["poly"], loops[j]["poly"]):
                parent[i] = j
                break

    def depth(i):
        d, k = 0, i
        while parent[k] != -1:
            k = parent[k]
            d += 1
        return d

    profiles = []
    for i, lp in enumerate(loops):
        d = depth(i)
        if d % 2 == 0:                      # 偶数层=实体(外轮廓或岛)
            prof = {"outer": lp, "holes": []}
            for k in range(len(loops)):
                if parent[k] == i and depth(k) % 2 == 1:   # 奇数层=孔
                    prof["holes"].append(loops[k])
                # depth 为偶数的子环=岛(体中体), 由它自己的那轮独立成 profile
            profiles.append(prof)
    return profiles, opens, sum(1 for s in segs if s.kind == "circle")


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


def _center_seen(grid, x, y, tol=LOOP_TOL):
    """量化网格 + 3×3 邻桶判同心: 已见返回 True, 未见登记并返回 False。

    (v1.35) 替代对 found 的 O(n²) 线性 any() 扫描——"空图层+全半径"配错
    时上万圆心的去重曾先行卡死, 护栏来不及救。
    """
    kx, ky = int(round(x / tol)), int(round(y / tol))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for px, py in grid.get((kx + dx, ky + dy), ()):
                if abs(px - x) < tol and abs(py - y) < tol:
                    return True
    grid.setdefault((kx, ky), []).append((x, y))
    return False


def collect_circle_anchors(layers, rule):
    """规则筛选圆/圆弧圆心 → [(cx, cy, r)]; 同心去重。

    v1.10: 定位图层=CXK 时改为"线中点"锚点——2D 图 CXK 层只画一条线,
    中点即放置点(接线盒规则; 半径字段对该层无意义, 忽略)。
    """
    lay = rule.get("layer") or ""
    if lay == "CXK":
        found, grid = [], {}
        for e in (layers.get("CXK") or []):
            if e.kind == "line":
                mx = (e.p1[0] + e.p2[0]) / 2.0
                my = (e.p1[1] + e.p2[1]) / 2.0
                if not _center_seen(grid, mx, my):
                    found.append((mx, my, 0.0))
        return found
    codes = [lay] if lay else LAYER_CODES
    rmin = float(rule.get("r_min", 0.0))
    rmax = float(rule.get("r_max", 9999.0))
    found, grid = [], {}
    for code in codes:
        for e in (layers.get(code) or []):
            if e.kind in ("circle", "arc") and (rmin - 1e-9) <= e.r <= (rmax + 1e-9):
                c = e.c
                if not _center_seen(grid, c[0], c[1]):
                    found.append((c[0], c[1], e.r))
    return found


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
