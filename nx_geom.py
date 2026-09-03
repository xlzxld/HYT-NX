# -*- coding: utf-8 -*-
"""
nx_geom.py —— DXF 解析 + 环链几何 + 几何指纹(纯 Python, 无 NX 依赖)
========================================================================

拆分自 nx_extrude_runner.py(§1 DXF 解析器 + §2 环链几何 + §5 里的几何指纹)。
本模块是"纯逻辑层": 不 import NXOpen, 可离线单测(见主脚本 --selftest)。

依赖契约(由主脚本注入为模块属性, 见 docs/模块拆分实施计划.md §1):
    LAYER_CODES   建模图层码列表(parse_dxf 据此判定"建模图层"vs"参考图层")
    LOOP_TOL      链端点连接容差(mm)

对外符号(主脚本再导出, 外部消费者 test/test_batch111.py 依赖 m.parse_dxf):
    DXLine DXArc DXCircle _read_dxf_text parse_dxf
    _pkey _near_keys find_chains loop_polygon poly_area _bbox
    point_in_poly _loop_in_loop organize_loops
    _q _nx_curve_fp _dxf_ent_fp dxf_fingerprints
"""

import math

# 以下两项由主脚本在加载时注入(见 nx_extrude_runner.py 的 _load_sub/_inject)。
# 缺省值仅为"万一被独立 import"时兜底, 正常路径恒被覆盖。
LAYER_CODES = ()
LOOP_TOL = 0.01


class DXLine(object):
    __slots__ = ("p1", "p2")
    kind = "line"
    def __init__(self, p1, p2):
        self.p1, self.p2 = p1, p2


class DXArc(object):
    __slots__ = ("c", "r", "a0", "a1")     # 角度: 弧度, CCW a0→a1
    kind = "arc"
    def __init__(self, c, r, a0, a1):
        self.c, self.r, self.a0, self.a1 = c, r, a0, a1
    @property
    def p1(self):
        return (self.c[0] + self.r * math.cos(self.a0),
                self.c[1] + self.r * math.sin(self.a0))
    @property
    def p2(self):
        return (self.c[0] + self.r * math.cos(self.a1),
                self.c[1] + self.r * math.sin(self.a1))


class DXCircle(object):
    __slots__ = ("c", "r")
    kind = "circle"
    def __init__(self, c, r):
        self.c, self.r = c, r


def _read_dxf_text(path):
    """DXF 文本读取: 优先 UTF-8, 失败按 GBK($DWGCODEPAGE=ANSI_936), 再失败 replace。"""
    with open(path, "rb") as _f:
        raw = _f.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", errors="replace")


def parse_dxf(path):
    """解析 DXF 的 ENTITIES 段(建模只认 LINE/CIRCLE/ARC, 与 offset_runner
    生成物一致)。

    返回 (layers, stats):
      layers: {图层名大写: [DXLine/DXArc/DXCircle, ...]}
      stats : {"ref_layers": {非建模图层名: 数},
               "unsupported": {实体类型: 数},       # 全部不支持的(含参考图层)
               "unsupported_model": 数,             # 其中的建模图层部分(弹窗口径)
               "nonplanar": 数, "total": 数}        # total 只计受支持实体
    """
    lines = _read_dxf_text(path).splitlines()
    n = len(lines)
    pairs = []
    for i in range(0, n - 1, 2):
        pairs.append((lines[i].strip(), lines[i + 1].strip("\r\n")))

    layers, stats = {}, {"ref_layers": {}, "unsupported": {},
                         "unsupported_model": 0, "nonplanar": 0, "total": 0}

    # 定位 ENTITIES 段(记起点, 实体切到 ENDSEC 为止)
    start = None
    for i in range(1, len(pairs)):
        if pairs[i] == ("2", "ENTITIES") and pairs[i - 1] == ("0", "SECTION"):
            start = i
            break
    if start is None:
        return layers, stats

    def entities_of(seg_pairs):
        """把 (code,val) 序列切成实体块 [{code: first-val}] 列表。

        全部实体类型都切块输出(含不支持的)——支持与否由上层判定并统计,
        保证 LWPOLYLINE 等被丢弃时有计数与警告, 不静默丢几何(v1.35)。
        """
        out, cur, ctype = [], None, None
        for code, val in seg_pairs:
            if code == "0":
                if ctype is not None:
                    out.append(cur)
                ctype = val
                cur = {"0": val}
            elif ctype is not None and code not in cur:
                cur[code] = val
        if ctype is not None:
            out.append(cur)
        return out

    seg2 = []
    for k in range(start, len(pairs)):   # 从 ENTITIES 段起, 截到 ENDSEC
        code, val = pairs[k]
        if code == "0" and val == "ENDSEC":
            break
        seg2.append((code, val))

    for e in entities_of(seg2):
        etype = e.get("0") or "?"
        if etype not in ("LINE", "CIRCLE", "ARC"):
            # LWPOLYLINE/SPLINE/INSERT 等: 计数并警告, 不静默丢(v1.35)
            layer = (e.get("8") or "0").upper()
            stats["unsupported"][etype] = \
                stats["unsupported"].get(etype, 0) + 1
            if layer in LAYER_CODES:
                stats["unsupported_model"] += 1
            continue
        stats["total"] += 1
        layer = (e.get("8") or "0").upper()
        if layer not in LAYER_CODES:
            stats["ref_layers"][layer] = stats["ref_layers"].get(layer, 0) + 1
            # 参考图层照常保留(导入 NX 但不建模)

        def fnum(key):
            return float(e.get(key, "0") or "0")

        z = fnum("30")
        if abs(z) > 1e-9:
            stats["nonplanar"] += 1
        try:
            if etype == "LINE":
                obj = DXLine((fnum("10"), fnum("20")), (fnum("11"), fnum("21")))
                if math.hypot(obj.p2[0] - obj.p1[0], obj.p2[1] - obj.p1[1]) < 1e-9:
                    continue                      # 零长线丢弃
            elif etype == "CIRCLE":
                obj = DXCircle((fnum("10"), fnum("20")), fnum("40"))
            else:                                  # ARC
                a0, a1 = math.radians(float(e["50"])), math.radians(float(e["51"]))
                if a1 <= a0:
                    a1 += 2.0 * math.pi
                obj = DXArc((fnum("10"), fnum("20")), fnum("40"), a0, a1)
        except (KeyError, ValueError) as ex:
            k = "<解析失败:%s>" % ex
            stats["unsupported"][k] = stats["unsupported"].get(k, 0) + 1
            continue
        layers.setdefault(layer, []).append(obj)
    return layers, stats


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
    from collections import defaultdict
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


def _q(v, nd=4):
    return round(float(v), nd)


def _nx_curve_fp(c):
    """NX 曲线 → 几何指纹(线=两端点; 弧=圆心,半径,起终角)。取不到返回 None。"""
    tname = type(c).__name__
    try:
        if tname == "Line":
            a, b = c.StartPoint, c.EndPoint
            p1, p2 = (_q(a.X), _q(a.Y)), (_q(b.X), _q(b.Y))
            return ("L",) + tuple(sorted((p1, p2)))
        if tname == "Arc":
            ctr = c.CenterPoint
            return ("A", _q(ctr.X), _q(ctr.Y), _q(c.Radius),
                    _q(c.StartAngle, 6), _q(c.EndAngle, 6))
    except Exception:
        return None
    return None


def _dxf_ent_fp(e):
    """DXF 实体 → 几何指纹(与 _nx_curve_fp 同一套量化, 可互相匹配)。"""
    if e.kind == "line":
        p1, p2 = (_q(e.p1[0]), _q(e.p1[1])), (_q(e.p2[0]), _q(e.p2[1]))
        return ("L",) + tuple(sorted((p1, p2)))
    if e.kind == "arc":
        return ("A", _q(e.c[0]), _q(e.c[1]), _q(e.r), _q(e.a0, 6), _q(e.a1, 6))
    # circle → 整圆弧(0..2π), 与 create_curves 的建法一致
    return ("A", _q(e.c[0]), _q(e.c[1]), _q(e.r), 0.0, round(2 * math.pi, 6))


def dxf_fingerprints(layers):
    """全部 DXF 实体的指纹多重集(旧版无标记曲线的迁移匹配用)。"""
    from collections import Counter
    fps = Counter()
    for ents in (layers or {}).values():
        for e in ents:
            fp = _dxf_ent_fp(e)
            if fp is not None:
                fps[fp] += 1
    return fps
