# -*- coding: utf-8 -*-
"""cad3d.geom.dxf_parser —— DXF 文本扫描切块与实体解析。"""

import math
from cad3d.core.constants import LAYER_CODES
from cad3d.geom.entities import DXLine, DXArc, DXCircle


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

    # 定位 ENTITIES 段(记起点, 实体切到 ENDSEC 为止)。
    # 段名比较对组值再 strip: 个别生成器会在组值后写填充空格,
    # 严格相等会定位失败 → 静默返回空 layers("共读到 0 个图形")
    start = None
    for i in range(1, len(pairs)):
        if (pairs[i][0] == "2" and pairs[i][1].strip() == "ENTITIES"
                and pairs[i - 1][0] == "0" and pairs[i - 1][1].strip() == "SECTION"):
            start = i
            break
    if start is None:
        return layers, stats

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
        layer = (e.get("8") or "0").upper()
        if layer not in LAYER_CODES:
            stats["ref_layers"][layer] = stats["ref_layers"].get(layer, 0) + 1
            # 参考图层照常保留(导入 NX 但不建模)

        def fnum(key):
            return float(e.get(key, "0") or "0")

        try:
            if etype == "LINE":
                # 非平面检测必须同时看起点(30)与终点(31)的 Z —— 曾只查 30,
                # (0,0,0)->(10,0,10) 这类斜线检测通过后被静默压平到 Z=0
                if abs(fnum("30")) > 1e-9 or abs(fnum("31")) > 1e-9:
                    stats["nonplanar"] += 1
                obj = DXLine((fnum("10"), fnum("20")), (fnum("11"), fnum("21")))
                if math.hypot(obj.p2[0] - obj.p1[0], obj.p2[1] - obj.p1[1]) < 1e-9:
                    continue                      # 零长线丢弃
            elif etype == "CIRCLE":
                if abs(fnum("30")) > 1e-9:
                    stats["nonplanar"] += 1
                r = fnum("40")
                if r <= 1e-9:
                    continue                      # 零半径圆丢弃
                obj = DXCircle((fnum("10"), fnum("20")), r)
            else:                                  # ARC
                if abs(fnum("30")) > 1e-9:
                    stats["nonplanar"] += 1
                r = fnum("40")
                if r <= 1e-9:
                    continue                      # 零半径弧丢弃
                a0, a1 = math.radians(float(e["50"])), math.radians(float(e["51"]))
                if abs(a1 - a0) < 1e-12:
                    continue                      # 退化弧(起终角相同)丢弃, 拉成整圆会包出多余实体
                if a1 < a0:
                    a1 += 2.0 * math.pi
                obj = DXArc((fnum("10"), fnum("20")), r, a0, a1)
        except (KeyError, ValueError) as ex:
            k = "<解析失败:%s>" % ex
            stats["unsupported"][k] = stats["unsupported"].get(k, 0) + 1
            continue
        # total 在丢弃判定之后累加, 只计真正进入建模/参考流程的受支持实体
        stats["total"] += 1
        layers.setdefault(layer, []).append(obj)
    return layers, stats
