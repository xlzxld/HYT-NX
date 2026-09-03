# -*- coding: utf-8 -*-
"""cad3d.geom.eval —— 纯几何断言、指纹提取与面健康体检评估。"""

import math
from collections import Counter


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
    fps = Counter()
    for ents in (layers or {}).values():
        for e in ents:
            fp = _dxf_ent_fp(e)
            if fp is not None:
                fps[fp] += 1
    return fps


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


def _jrt_sides(z_start, z_end, bottom):
    """加热条两侧区间: 顶侧=(start,end); 底侧=底面镜像(入侵量=end-start)。

    (与期刊"镜像到板另一侧"工序等效: 两侧对称。)
    """
    intr = z_end - z_start                      # 顶侧入侵量(带方向)
    return [("T", z_start, z_end), ("B", bottom, bottom - intr)]
