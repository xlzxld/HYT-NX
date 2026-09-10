# -*- coding: utf-8 -*-
r"""tools/probe_jrtfbx.py —— JRTFBX 删面定位离线体检(不依赖 NX, 随时可跑)。

用途: 2D 图纸改过一版就复核一次, 确认三件事——
  1. JRTFBX 层画了几条、和 JRT 层的封闭线是否重合(重合会被并入逻辑丢弃);
  2. JRT 轮廓能不能自己闭合出条体链, 有几条开链被放弃(不建模);
  3. 删面锚点(标记点)能否命中, 有没有超限。

用法(NX 不开也能跑):
    python tools/probe_jrtfbx.py                  # 自动取 logs/ 下最新 .dxf
    python tools/probe_jrtfbx.py 路径\图纸.dxf     # 指定图纸

控制台用 GBK 打印中文; 报告同时落盘 logs/jrtfbx_probe_report.txt(UTF-8)。
"""

import io
import math
import os
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cad3d.core.constants import DYNAMIC_START, REF_LAYER_TABLE, assign_layers
from cad3d.geom.dxf_parser import parse_dxf
from cad3d.geom.topo import (
    _bbox,
    _chain_connectors,
    _chain_outlet_mids,
    _contour_outlet_mids,
    _fbx_anchor_points,
    _marker_mids_for_chains,
    _merge_marker_lines,
    _merge_open_chains,
    find_chains,
)

MARK_MARGIN = 10.0     # 与 jrt.py 的标记就近分配余量一致
BLEND_R = 3.9          # 倒圆起始 R(仅用于算门控值, 与实际参数无关)


def _latest_dxf():
    """默认图纸: 项目根目录 + logs/ 下最新的 .dxf。

    排除生成物: _ 开头的(DWG 转换缓存)与 sample_layers.dxf(离线自测每次
    重写它, 会被误当最新图纸)。不用记忆文件里的 dxf_path —— 它常常停在
    上一次执行的旧图上, 反而指向错的图。
    """
    cands = []
    for d in (_ROOT, os.path.join(_ROOT, "logs")):
        try:
            cands += [os.path.join(d, n) for n in os.listdir(d)
                      if n.lower().endswith(".dxf") and not n.startswith("_")
                      and not n.startswith("sample_layers")]
        except OSError:
            continue
    if not cands:
        return ""
    return max(cands, key=os.path.getmtime)


def _same_as_jrt(fe, jrt):
    """fe 是否与 JRT 层某条直线重合——判定复用 jrt.py 同一套(top)。"""
    return bool(_merge_marker_lines(jrt, [fe])[1])


def _nearest_dev(fe, jrt):
    """fe 与 JRT 层最近直线的端点最大偏差; 没有直线可比→None。"""
    best = None
    for u in jrt:
        if u.kind != "line":
            continue
        d1 = max(math.hypot(fe.p1[0] - u.p1[0], fe.p1[1] - u.p1[1]),
                 math.hypot(fe.p2[0] - u.p2[0], fe.p2[1] - u.p2[1]))
        d2 = max(math.hypot(fe.p1[0] - u.p2[0], fe.p1[1] - u.p2[1]),
                 math.hypot(fe.p2[0] - u.p1[0], fe.p2[1] - u.p1[1]))
        d = min(d1, d2)
        if best is None or d < best:
            best = d
    return best


def _seglen(e):
    if e.kind == "line":
        return math.hypot(e.p2[0] - e.p1[0], e.p2[1] - e.p1[1])
    return e.r * abs(e.a1 - e.a0)


def probe(dxf_path):
    """返回体检报告行列表(纯文本)。"""
    out = []
    out.append("图纸: %s (%d 字节)" % (dxf_path, os.path.getsize(dxf_path)))
    layers, stats = parse_dxf(dxf_path)
    out.append("实体 %d 个; 不支持的实体类型: %s; Z≠0: %d"
               % (stats["total"], stats["unsupported"] or "无", stats["nonplanar"]))
    out.append("识别到的图层: %s" % ", ".join(
        "%s×%d" % (k, len(v)) for k, v in sorted(layers.items())))

    fbx = layers.get("JRTFBX") or []
    jrt = layers.get("JRT") or []

    out.append("")
    out.append("── 1. JRTFBX 标记层 ──")
    if not fbx:
        out.append("  图纸里没有 JRTFBX 图层 → 删面锚点只能靠轮廓推断。")
    else:
        kinds = Counter(e.kind for e in fbx)
        out.append("  %d 条: %s" % (len(fbx), dict(kinds)))
        if kinds.get("arc") or kinds.get("circle"):
            out.append("  ⚠ 有非直线实体: 并入时按原始下标取曲线, "
                       "非直线不参与(已修, 但仍建议标记层只放直线)。")
        pts = _fbx_anchor_points(fbx)
        out.append("  标记点 %d 个: %s"
                   % (len(pts), ", ".join("(%.2f,%.2f)" % p for p in pts)))
        for e in fbx:
            if e.kind != "line":
                continue
            hit = _same_as_jrt(e, jrt)
            dev = ""
            if hit:
                dev = "(与 JRT 线偏差 %.4f)" % _nearest_dev(e, jrt)
            out.append("    线 L=%.2f (%.2f,%.2f)-(%.2f,%.2f) %s"
                       % (_seglen(e), e.p1[0], e.p1[1], e.p2[0], e.p2[1],
                          "重合于 JRT 层" + dev if hit else "JRT 层没有对应线(靠它封口)"))

    out.append("")
    out.append("── 2. 条轮廓闭链(决定拉伸) ──")
    _add, _dup, _oth = _merge_marker_lines(jrt, fbx)
    added = [fbx[k] for k in _add]
    dropped = [fbx[k] for k in _dup]
    out.append("  并入复算: JRTFBX 直线 %d 条 → 新增 %d / 与 JRT 重合丢弃 %d"
               % (len(_add) + len(_dup), len(added), len(dropped)))
    if dropped and not added:
        out.append("  ⚠ 全部重合被丢弃: 条轮廓完全靠 JRT 层自己的线成形, "
                   "JRTFBX 只当锚点用(代码会打一行大白话说明)。")

    ents = list(jrt) + list(added)
    closed0, opens0 = find_chains(jrt)
    closed, opens = find_chains(ents)
    out.append("  仅 JRT 层    : 闭链 %d / 开链 %d" % (len(closed0), len(opens0)))
    out.append("  JRT+JRTFBX  : 闭链 %d / 开链 %d" % (len(closed), len(opens)))
    if opens:
        c_extra, b_jobs, o_logs = _merge_open_chains(opens, ents)
        out.append("  开链修复: 补闭 %d / 桥接 %d 组 / 放弃 %d 条"
                   % (len(c_extra), len(b_jobs), len(o_logs)))
        closed = list(closed) + c_extra + [j[0] for j in b_jobs]
    for ci, ch in enumerate(closed):
        out.append("    闭链%d: %d 段" % (ci + 1, len(ch)))
    for oi, ch in enumerate(opens):
        tips = []
        for i, _r in ch:
            e = ents[i]
            tips += [e.p1, e.p2] if e.kind != "circle" else []
        cnt = Counter((round(x, 3), round(y, 3)) for x, y in tips)
        free = [p for p, c in cnt.items() if c == 1]
        out.append("    ⚠ 开链%d: %d 段 展开长≈%.0fmm 不参与建模; 断口 %s"
                   % (oi + 1, len(ch), sum(_seglen(ents[i]) for i, _r in ch),
                      free))

    out.append("")
    out.append("── 3. 删面锚点 ──")
    if not closed:
        out.append("  无闭链 → 不会建模, 锚点无意义。")
        return out
    boxes = []
    for ch in closed:
        ps = []
        for i, _r in ch:
            e = ents[i]
            if e.kind == "circle":
                ps += [(e.c[0] - e.r, e.c[1] - e.r), (e.c[0] + e.r, e.c[1] + e.r)]
            else:
                ps += [e.p1, e.p2]
        boxes.append(_bbox(ps))
    pts = _fbx_anchor_points(fbx)
    per, ign = _marker_mids_for_chains(boxes, pts, MARK_MARGIN)
    for w in ign:
        out.append("  ⚠ %s" % w)
    gate = 2.5 * max(BLEND_R, 1.0) + 2.0
    for ci, ch in enumerate(closed):
        inf = (_chain_outlet_mids(ch, ents) or _contour_outlet_mids(ch, ents)
               or _chain_connectors(ch, ents))
        use = per[ci] if per else []
        out.append("  链%d: 锚点来源=%s, %d 个 %s"
                   % (ci + 1, "JRTFBX 标记" if use else "轮廓推断", len(use or inf),
                      [(round(m[0], 2), round(m[1], 2))
                       for m in (use or inf)]))
        if use:
            for m in use:
                dmin = min([math.hypot(m[0] - v[0], m[1] - v[1])
                            for v in inf] or [9e9])
                out.append("      标记(%.2f,%.2f) 距推断唇线 %.2f (门控 %.2f) %s"
                           % (m[0], m[1], dmin, gate,
                              "命中" if dmin <= gate else "⚠ 超限(仍会被用作锚点!)"))
        if not inf and not use:
            out.append("      没有可用锚点 → 这根条不会删面。")

    out.append("")
    out.append("── 4. 图层号 ──")
    mp = assign_layers(sorted(layers.keys()))
    out.append("  JRTFBX → NX 图层 %s (参考图层登记表: %s)"
               % (mp.get("JRTFBX"), [r[0] for r in REF_LAYER_TABLE]))
    out.append("  提示: 登记过的图层号是固定的; 没登记的走动态分配(%s 起按名字"
               "排序), 图纸增删图层会改号。" % DYNAMIC_START)
    return out


def main():
    dxf = sys.argv[1] if len(sys.argv) > 1 else _latest_dxf()
    if not dxf or not os.path.isfile(dxf):
        print("没找到 DXF 图纸: 请传路径, 或把图纸放进 logs/。")
        return 2
    lines = probe(dxf)
    text = "\n".join(lines)
    rep = os.path.join(_ROOT, "logs", "jrtfbx_probe_report.txt")
    try:
        os.makedirs(os.path.dirname(rep), exist_ok=True)
        with io.open(rep, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError as ex:
        print("报告落盘失败: %s" % ex)
    for ln in lines:
        try:
            print(ln)
        except UnicodeEncodeError:      # 控制台编码接不住时退到报告文件
            print(ln.encode("gbk", "replace").decode("gbk", "replace"))
    print()
    print("报告已落盘 -> %s" % rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
